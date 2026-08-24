const LAB_DIR = @__DIR__
if abspath(PROGRAM_FILE) == @__FILE__
    import Pkg
    Pkg.activate(LAB_DIR)
    if !("--no-instantiate" in ARGS)
        Pkg.instantiate()
    end
end

using Bonito
using Printf
using WGLMakie

const DOM = Bonito.DOM
const Slider = WGLMakie.Makie.Slider

const GRAVITY = 9.80665
const FIGURE_WIDTH = 960
const FIGURE_HEIGHT = 760

const CYAN = RGBf(0.18, 0.78, 0.92)
const PINK = RGBf(0.94, 0.35, 0.50)
const AMBER = RGBf(1.00, 0.72, 0.24)
const GREEN = RGBf(0.36, 0.82, 0.55)
const VIOLET = RGBf(0.61, 0.48, 0.92)
const MUTED = RGBf(0.58, 0.62, 0.70)
const PANEL_BG = RGBf(0.075, 0.085, 0.105)
const CJK_PROBE_TEXT = "转动惯量扭摆三线摆平行轴定理复摆周期拟合不确定度"
const HEALTH_MARKER = "physics-experiment:rotational-inertia"
const WGL_SHADER_FILES = (
    "mesh.frag",
    "mesh.vert",
    "particles.vert",
    "sprites.frag",
    "sprites.vert",
    "volume.frag",
    "volume.vert",
    "voxel.frag",
    "voxel.vert",
)

function load_packaged_wgl_shaders!()
    asset_dir = normpath(joinpath(Sys.BINDIR, "..", "share", "photoelectric", "wglmakie_assets"))
    isdir(asset_dir) || return false
    for name in WGL_SHADER_FILES
        path = joinpath(asset_dir, name)
        isfile(path) || error("缺少 WGLMakie 着色器文件：$(path)")
        WGLMakie.ALL_SHADERS[name] = read(path, String)
    end
    println("已从便携运行时加载 WGLMakie 着色器：$(asset_dir)")
    return true
end

function font_supports_cjk(path)
    try
        font = WGLMakie.Makie.FreeTypeAbstraction.FTFont(String(path))
        return all(
            character -> WGLMakie.Makie.FreeTypeAbstraction.glyph_index(font, character) != 0,
            CJK_PROBE_TEXT,
        )
    catch
        return false
    end
end

function first_cjk_font(candidates)
    for candidate in candidates
        isnothing(candidate) && continue
        path = String(candidate)
        !isempty(path) && isfile(path) && font_supports_cjk(path) && return path
    end
    return nothing
end

function fontconfig_match(pattern)
    executable = Sys.which("fc-match")
    isnothing(executable) && return nothing
    try
        output = read(Cmd([executable, "-f", "%{file}\n", pattern]), String)
        candidates = [String(strip(line)) for line in split(output, '\n') if !isempty(strip(line))]
        return isempty(candidates) ? nothing : first_cjk_font(candidates)
    catch
        return nothing
    end
end

function cjk_font_family()
    runtime_font = normpath(joinpath(LAB_DIR, "..", "..", "..", ".runtime", "fonts", "NotoSansCJKsc-Regular.otf"))
    bundled_font = normpath(joinpath(LAB_DIR, "..", "..", "assets", "fonts", "NotoSansCJKsc-Regular.otf"))
    julia_font = normpath(joinpath(Sys.BINDIR, "..", "share", "photoelectric", "fonts", "NotoSansCJKsc-Regular.otf"))
    regular = first_cjk_font([
        get(ENV, "PHYSICS_CJK_FONT", ""), runtime_font, bundled_font, julia_font,
        isempty(get(ENV, "WINDIR", "")) ? "" : joinpath(ENV["WINDIR"], "Fonts", "msyh.ttc"),
        "/System/Library/Fonts/PingFang.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/google-noto-cjk-fonts/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/google-noto-vf/NotoSansCJK-VF.ttf",
        fontconfig_match("Noto Sans CJK SC:lang=zh-cn"),
    ])
    isnothing(regular) && error("未找到真正包含中文字形的字体。请通过 PHYSICS_CJK_FONT 指定 Noto Sans CJK SC 字体文件。")
    bold = first_cjk_font([
        get(ENV, "PHYSICS_CJK_FONT", ""), runtime_font, bundled_font, julia_font,
        isempty(get(ENV, "WINDIR", "")) ? "" : joinpath(ENV["WINDIR"], "Fonts", "msyhbd.ttc"),
        "/System/Library/Fonts/PingFang.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc",
        fontconfig_match("Noto Sans CJK SC Bold:lang=zh-cn"),
    ])
    isnothing(bold) && (bold = regular)
    return (; regular, bold)
end

function configure_theme!()
    fonts = cjk_font_family()
    set_theme!(Theme(
        fontsize = 14,
        font = fonts.regular,
        fonts = (; regular = fonts.regular, bold = fonts.bold),
        textcolor = :white,
        backgroundcolor = RGBf(0.045, 0.052, 0.065),
        Axis = (
            backgroundcolor = PANEL_BG,
            xgridcolor = (:white, 0.07), ygridcolor = (:white, 0.07),
            spinecolor = (:white, 0.18), xtickcolor = (:white, 0.25),
            ytickcolor = (:white, 0.25), topspinevisible = false, rightspinevisible = false,
        ),
    ))
end

function base_figure()
    configure_theme!()
    figure = Figure(size = (FIGURE_WIDTH, FIGURE_HEIGHT), figure_padding = (18, 18, 22, 32))
    controls = GridLayout()
    metrics = GridLayout()
    figure[2, 1:2] = controls
    figure[3, 1:2] = metrics
    rowsize!(figure.layout, 1, 380)
    rowsize!(figure.layout, 2, 140)
    rowsize!(figure.layout, 3, 110)
    colsize!(figure.layout, 1, Relative(0.5))
    colsize!(figure.layout, 2, Relative(0.5))
    rowgap!(figure.layout, 6)
    colgap!(figure.layout, 10)
    return figure, controls, metrics
end

function add_slider!(grid, row, label, range, startvalue, formatter)
    Label(grid[row, 1], label, halign = :right)
    slider = Slider(grid[row, 2]; range, startvalue, update_while_dragging = false)
    Label(grid[row, 3], lift(formatter, slider.value), halign = :left)
    colsize!(grid, 1, Relative(0.19))
    colsize!(grid, 2, Relative(0.65))
    colsize!(grid, 3, Relative(0.16))
    rowsize!(grid, row, 24)
    rowgap!(grid, 4)
    return slider
end

function add_metrics!(grid, values, detail)
    for (column, value) in enumerate(values)
        Label(grid[1, column], value, halign = :left, fontsize = 13)
        colsize!(grid, column, Relative(0.25))
    end
    Label(grid[2, 1:4], detail; color = MUTED, halign = :left, fontsize = 12.5, tellwidth = false)
    rowsize!(grid, 1, 28)
    rowsize!(grid, 2, 48)
    rowgap!(grid, 8)
    return nothing
end

function linear_fit(x, y)
    length(x) == length(y) || throw(ArgumentError("拟合数据长度不一致"))
    length(x) >= 3 || throw(ArgumentError("线性拟合至少需要三个测量点"))
    xf = Float64.(x)
    yf = Float64.(y)
    xbar = sum(xf) / length(xf)
    ybar = sum(yf) / length(yf)
    centered = xf .- xbar
    sxx = sum(abs2, centered)
    sxx > 0 || throw(ArgumentError("拟合自变量不能全部相同"))
    slope = sum(centered .* (yf .- ybar)) / sxx
    intercept = ybar - slope * xbar
    predicted = intercept .+ slope .* xf
    residuals = yf .- predicted
    residual_variance = sum(abs2, residuals) / (length(xf) - 2)
    slope_uncertainty = sqrt(max(residual_variance, 0.0) / sxx)
    intercept_uncertainty = sqrt(max(residual_variance, 0.0) * (1.0 / length(xf) + xbar^2 / sxx))
    slope_intercept_covariance = -xbar * max(residual_variance, 0.0) / sxx
    total_variation = sum(abs2, yf .- ybar)
    r_squared = total_variation > 0 ? 1.0 - sum(abs2, residuals) / total_variation : 1.0
    return (;
        slope, intercept, predicted, residuals, residual_variance,
        slope_uncertainty, intercept_uncertainty, slope_intercept_covariance,
        r_squared,
    )
end

disk_inertia(mass_kg, radius_m) = 0.5 * Float64(mass_kg) * Float64(radius_m)^2

function torsion_model(kappa_mnm, platform_inertia_gcm2, mass_kg, radius_cm, damping)
    kappa = Float64(kappa_mnm) * 1.0e-3
    platform_inertia = Float64(platform_inertia_gcm2) * 1.0e-7
    radius_m = Float64(radius_cm) * 1.0e-2
    object_inertia = disk_inertia(mass_kg, radius_m)
    total_inertia = platform_inertia + object_inertia
    period_s = 2pi * sqrt(total_inertia / kappa)
    measured_period_s = period_s * (1.0 + 0.0015 * sin(2.7 * Float64(radius_cm)))
    measured_inertia = kappa * measured_period_s^2 / (4pi^2) - platform_inertia
    time_s = collect(range(0.0, 5.0 * period_s; length = 360))
    angle_deg = 8.0 .* exp.(-Float64(damping) .* time_s) .* cos.(2pi .* time_s ./ period_s)
    radius_values_cm = collect(range(3.0, 9.0; length = 100))
    period_values_s = [2pi * sqrt((platform_inertia + disk_inertia(mass_kg, radius * 1.0e-2)) / kappa) for radius in radius_values_cm]
    return (;
        kappa, platform_inertia, object_inertia, total_inertia, period_s,
        measured_period_s, measured_inertia, time_s, angle_deg,
        radius_values_cm, period_values_s,
        relative_error_percent = 100.0 * (measured_inertia - object_inertia) / object_inertia,
    )
end

function torsion_figure()
    figure, controls, metrics = base_figure()
    oscillation_axis = Axis(
        figure[1, 1],
        title = "扭摆角位移衰减",
        xlabel = "时间 t / s",
        ylabel = "角位移 θ / °",
    )
    calibration_axis = Axis(
        figure[1, 2],
        title = "圆盘半径对周期的影响",
        xlabel = "圆盘半径 R / cm",
        ylabel = "周期 T / s",
    )

    kappa = add_slider!(controls, 1, "扭转常量 κ", 4.0:0.5:14.0, 8.0, value -> @sprintf("%.1f mN·m/rad", value))
    platform = add_slider!(controls, 2, "空台 I₀", 500:50:1500, 900, value -> @sprintf("%.0f g·cm²", value))
    mass = add_slider!(controls, 3, "圆盘质量 m", 0.20:0.05:0.80, 0.50, value -> @sprintf("%.2f kg", value))
    radius = add_slider!(controls, 4, "圆盘半径 R", 3.0:0.5:9.0, 6.0, value -> @sprintf("%.1f cm", value))
    damping = add_slider!(controls, 5, "阻尼系数 β", 0.00:0.01:0.08, 0.03, value -> @sprintf("%.2f s⁻¹", value))

    data = lift(kappa.value, platform.value, mass.value, radius.value, damping.value) do k, i0, m, r, beta
        torsion_model(Float64(k), Float64(i0), Float64(m), Float64(r), Float64(beta))
    end
    lines!(oscillation_axis, lift(value -> value.time_s, data), lift(value -> value.angle_deg, data), color = CYAN, linewidth = 2.5)
    hlines!(oscillation_axis, [0.0], color = (:white, 0.25), linestyle = :dash)
    lines!(calibration_axis, lift(value -> value.radius_values_cm, data), lift(value -> value.period_values_s, data), color = GREEN, linewidth = 2.7, label = "理论曲线")
    scatter!(calibration_axis, lift(value -> [Float64(radius.value[])], data), lift(value -> [value.measured_period_s], data), color = PINK, markersize = 16, label = "周期测量")
    axislegend(calibration_axis, position = :lt, framevisible = false)

    values = (
        lift(value -> @sprintf("T = %.4f s", value.measured_period_s), data),
        lift(value -> @sprintf("I₀ = %.3e kg·m²", value.platform_inertia), data),
        lift(value -> @sprintf("I测 = %.3e kg·m²", value.measured_inertia), data),
        lift(value -> @sprintf("相对误差 %+.3f%%", value.relative_error_percent), data),
    )
    detail = "扭摆满足 T=2π√((I₀+I)/κ)，故待测件转动惯量 I=κT²/(4π²)-I₀；阻尼仅改变振幅包络，弱阻尼下对周期的一阶影响可忽略。"
    add_metrics!(metrics, values, detail)
    return figure
end

function trifilar_model(mass_kg, upper_radius_cm, lower_radius_cm, vertical_spacing_cm, timing_bias_ms)
    mass = Float64(mass_kg)
    upper_radius_m = Float64(upper_radius_cm) * 1.0e-2
    lower_radius_m = Float64(lower_radius_cm) * 1.0e-2
    vertical_spacing_m = Float64(vertical_spacing_cm) * 1.0e-2
    true_inertia = disk_inertia(mass, lower_radius_m)
    restoring_constant = mass * GRAVITY * upper_radius_m * lower_radius_m / vertical_spacing_m
    period_s = 2pi * sqrt(true_inertia / restoring_constant)
    measured_period_s = period_s + Float64(timing_bias_ms) * 1.0e-3
    measured_inertia = mass * GRAVITY * upper_radius_m * lower_radius_m * measured_period_s^2 /
                       (4pi^2 * vertical_spacing_m)
    time_s = collect(range(0.0, 4.0 * period_s; length = 320))
    angle_deg = 7.0 .* cos.(2pi .* time_s ./ period_s)
    phi = collect(range(0.0, 2pi; length = 180))
    upper_circle_x = upper_radius_m .* cos.(phi) .* 100.0
    upper_circle_y = upper_radius_m .* sin.(phi) .* 100.0
    lower_circle_x = lower_radius_m .* cos.(phi) .* 100.0
    lower_circle_y = lower_radius_m .* sin.(phi) .* 100.0
    twist = deg2rad(12.0)
    anchor_angles = [0.0, 2pi / 3, 4pi / 3]
    top_x = upper_radius_m .* cos.(anchor_angles) .* 100.0
    top_y = upper_radius_m .* sin.(anchor_angles) .* 100.0
    bottom_x = lower_radius_m .* cos.(anchor_angles .+ twist) .* 100.0
    bottom_y = lower_radius_m .* sin.(anchor_angles .+ twist) .* 100.0
    return (;
        mass, upper_radius_m, lower_radius_m, vertical_spacing_m, true_inertia,
        restoring_constant, period_s, measured_period_s, measured_inertia,
        time_s, angle_deg, upper_circle_x, upper_circle_y, lower_circle_x,
        lower_circle_y, top_x, top_y, bottom_x, bottom_y,
        relative_error_percent = 100.0 * (measured_inertia - true_inertia) / true_inertia,
    )
end

function trifilar_figure()
    figure, controls, metrics = base_figure()
    geometry_axis = Axis(
        figure[1, 1],
        title = "三线摆上下悬点几何",
        xlabel = "x / cm",
        ylabel = "y / cm",
        aspect = DataAspect(),
    )
    motion_axis = Axis(
        figure[1, 2],
        title = "小角扭转振动",
        xlabel = "时间 t / s",
        ylabel = "转角 θ / °",
    )

    mass = add_slider!(controls, 1, "系统质量 m", 1.0:0.25:4.0, 2.0, value -> @sprintf("%.2f kg", value))
    upper = add_slider!(controls, 2, "上盘悬点半径 R", 8.0:0.5:16.0, 12.0, value -> @sprintf("%.1f cm", value))
    lower = add_slider!(controls, 3, "下盘悬点半径 r", 6.0:0.5:14.0, 10.0, value -> @sprintf("%.1f cm", value))
    height = add_slider!(controls, 4, "上下盘竖直间距 H", 40:5:90, 60, value -> @sprintf("%.0f cm", value))
    timing = add_slider!(controls, 5, "周期偏差 ΔT", -10:1:10, 3, value -> @sprintf("%+.0f ms", value))

    data = lift(mass.value, upper.value, lower.value, height.value, timing.value) do m, r_upper, r_lower, vertical_height, bias
        trifilar_model(Float64(m), Float64(r_upper), Float64(r_lower), Float64(vertical_height), Float64(bias))
    end
    lines!(geometry_axis, lift(value -> value.upper_circle_x, data), lift(value -> value.upper_circle_y, data), color = CYAN, linewidth = 2.2, label = "上盘悬点圆")
    lines!(geometry_axis, lift(value -> value.lower_circle_x, data), lift(value -> value.lower_circle_y, data), color = AMBER, linewidth = 2.2, label = "下盘悬点圆")
    scatter!(geometry_axis, lift(value -> value.top_x, data), lift(value -> value.top_y, data), color = CYAN, markersize = 13)
    scatter!(geometry_axis, lift(value -> value.bottom_x, data), lift(value -> value.bottom_y, data), color = PINK, markersize = 13)
    for index in 1:3
        lines!(
            geometry_axis,
            lift(value -> [value.top_x[index], value.bottom_x[index]], data),
            lift(value -> [value.top_y[index], value.bottom_y[index]], data),
            color = GREEN,
            linewidth = 2,
        )
    end
    axislegend(geometry_axis, position = :lt, framevisible = false, labelsize = 10)
    lines!(motion_axis, lift(value -> value.time_s, data), lift(value -> value.angle_deg, data), color = VIOLET, linewidth = 2.5)
    hlines!(motion_axis, [0.0], color = (:white, 0.25), linestyle = :dash)

    values = (
        lift(value -> @sprintf("T = %.4f s", value.measured_period_s), data),
        lift(value -> @sprintf("κg = %.4f N·m/rad", value.restoring_constant), data),
        lift(value -> @sprintf("I测 = %.3e kg·m²", value.measured_inertia), data),
        lift(value -> @sprintf("相对误差 %+.3f%%", value.relative_error_percent), data),
    )
    detail = "三线摆小角近似下重力回复常量 κg=mgRr/H，T=2π√(I/κg)，因此 I=mgRrT²/(4π²H)；H 为上下悬点平面的竖直间距，并非 R≠r 时的悬线斜长。"
    add_metrics!(metrics, values, detail)
    return figure
end

function parallel_axis_model(mass_kg, radius_cm, offset_cm, kappa_mnm, noise_gcm2)
    mass = Float64(mass_kg)
    radius_m = Float64(radius_cm) * 1.0e-2
    selected_offset_m = Float64(offset_cm) * 1.0e-2
    kappa = Float64(kappa_mnm) * 1.0e-3
    center_inertia = disk_inertia(mass, radius_m)
    offsets_m = collect(0.0:0.015:0.12)
    squared_offsets_m2 = offsets_m .^ 2
    true_inertias = center_inertia .+ mass .* squared_offsets_m2
    noise_kgm2 = Float64(noise_gcm2) * 1.0e-7
    patterns = [0.00, 0.72, -0.48, 0.31, -0.82, 0.54, -0.20, 0.38, -0.11]
    measured_inertias = true_inertias .+ noise_kgm2 .* patterns
    fit = linear_fit(squared_offsets_m2, measured_inertias)
    selected_inertia = center_inertia + mass * selected_offset_m^2
    selected_period_s = 2pi * sqrt(selected_inertia / kappa)
    phi = collect(range(0.0, 2pi; length = 180))
    body_x_cm = Float64(offset_cm) .+ Float64(radius_cm) .* cos.(phi)
    body_y_cm = Float64(radius_cm) .* sin.(phi)
    return (;
        mass, radius_m, selected_offset_m, kappa, center_inertia, offsets_m,
        squared_offsets_m2, true_inertias, measured_inertias, fit,
        selected_inertia, selected_period_s, body_x_cm, body_y_cm,
        fitted_mass_kg = fit.slope,
        fitted_center_inertia = fit.intercept,
        mass_error_percent = 100.0 * (fit.slope - mass) / mass,
    )
end

function parallel_axis_figure()
    figure, controls, metrics = base_figure()
    geometry_axis = Axis(
        figure[1, 1],
        title = "偏心转轴与圆盘质心",
        xlabel = "x / cm",
        ylabel = "y / cm",
        aspect = DataAspect(),
    )
    fit_axis = Axis(
        figure[1, 2],
        title = "I-d² 线性验证",
        xlabel = "轴距平方 d² / m²",
        ylabel = "转动惯量 I / kg·m²",
    )

    mass = add_slider!(controls, 1, "圆盘质量 m", 0.20:0.05:0.80, 0.50, value -> @sprintf("%.2f kg", value))
    radius = add_slider!(controls, 2, "圆盘半径 R", 3.0:0.5:7.0, 5.0, value -> @sprintf("%.1f cm", value))
    offset = add_slider!(controls, 3, "转轴偏移 d", 0.0:0.5:12.0, 6.0, value -> @sprintf("%.1f cm", value))
    kappa = add_slider!(controls, 4, "扭转常量 κ", 4.0:0.5:14.0, 8.0, value -> @sprintf("%.1f mN·m/rad", value))
    noise = add_slider!(controls, 5, "惯量读数散布", 0:10:100, 40, value -> @sprintf("%.0f g·cm²", value))

    data = lift(mass.value, radius.value, offset.value, kappa.value, noise.value) do m, r, d, k, scatter
        parallel_axis_model(Float64(m), Float64(r), Float64(d), Float64(k), Float64(scatter))
    end
    lines!(geometry_axis, lift(value -> value.body_x_cm, data), lift(value -> value.body_y_cm, data), color = CYAN, linewidth = 3, label = "圆盘轮廓")
    scatter!(geometry_axis, [0.0], [0.0], color = AMBER, markersize = 18, label = "转轴 O")
    scatter!(geometry_axis, lift(value -> [value.selected_offset_m * 100.0], data), [0.0], color = PINK, markersize = 18, label = "质心 C")
    lines!(geometry_axis, lift(value -> [0.0, value.selected_offset_m * 100.0], data), [0.0, 0.0], color = GREEN, linewidth = 3)
    xlims!(geometry_axis, -8.0, 20.0)
    ylims!(geometry_axis, -10.0, 10.0)
    axislegend(geometry_axis, position = :lt, framevisible = false, labelsize = 10)

    scatter!(fit_axis, lift(value -> value.squared_offsets_m2, data), lift(value -> value.measured_inertias, data), color = CYAN, markersize = 12, label = "模拟测量")
    lines!(fit_axis, lift(value -> value.squared_offsets_m2, data), lift(value -> value.fit.predicted, data), color = GREEN, linewidth = 2.7, label = "自由截距拟合")
    scatter!(fit_axis, lift(value -> [value.selected_offset_m^2], data), lift(value -> [value.selected_inertia], data), color = PINK, markersize = 16, label = "当前轴距")
    axislegend(fit_axis, position = :lt, framevisible = false, labelsize = 10)

    values = (
        lift(value -> @sprintf("T(d)=%.4f s", value.selected_period_s), data),
        lift(value -> @sprintf("I_C=%.3e kg·m²", value.fitted_center_inertia), data),
        lift(value -> @sprintf("拟合质量 %.4f kg", value.fitted_mass_kg), data),
        lift(value -> @sprintf("R² = %.6f", value.fit.r_squared), data),
    )
    detail = lift(data) do value
        @sprintf("平行轴定理 I_O=I_C+md²；对 I-d² 作自由截距拟合，斜率给出质量 m，截距给出质心轴惯量 I_C。当前斜率相对偏差 %+.3f%%。", value.mass_error_percent)
    end
    add_metrics!(metrics, values, detail)
    return figure
end

function pendulum_fit_model(mass_kg, gyration_radius_cm, selected_pivot_cm, period_u_ms, pivot_u_mm)
    mass = Float64(mass_kg)
    gyration_radius_m = Float64(gyration_radius_cm) * 1.0e-2
    selected_pivot_m = Float64(selected_pivot_cm) * 1.0e-2
    period_u_s = Float64(period_u_ms) * 1.0e-3
    pivot_u_m = Float64(pivot_u_mm) * 1.0e-3
    center_inertia = mass * gyration_radius_m^2
    pivot_distances_m = collect(range(0.08, 0.32; length = 11))
    true_periods_s = [
        2pi * sqrt((center_inertia + mass * h^2) / (mass * GRAVITY * h))
        for h in pivot_distances_m
    ]
    patterns = [0.0, 0.62, -0.44, 0.28, -0.71, 0.51, -0.19, 0.39, -0.27, 0.16, -0.08]
    measured_periods_s = true_periods_s .+ period_u_s .* patterns
    x_h2_m2 = pivot_distances_m .^ 2
    y_t2h_s2m = measured_periods_s .^ 2 .* pivot_distances_m
    fit = linear_fit(x_h2_m2, y_t2h_s2m)
    fitted_g = 4pi^2 / fit.slope
    fitted_k2 = fit.intercept / fit.slope
    fitted_k2 > 0 || throw(ArgumentError("拟合截距必须给出正的回转半径平方"))
    fitted_radius_m = sqrt(fitted_k2)
    fitted_center_inertia = mass * fitted_k2
    d_i_c_d_slope = -mass * fit.intercept / fit.slope^2
    d_i_c_d_intercept = mass / fit.slope
    fitted_center_inertia_variance =
        d_i_c_d_slope^2 * fit.slope_uncertainty^2 +
        d_i_c_d_intercept^2 * fit.intercept_uncertainty^2 +
        2.0 * d_i_c_d_slope * d_i_c_d_intercept * fit.slope_intercept_covariance
    fitted_center_inertia_uncertainty = sqrt(max(fitted_center_inertia_variance, 0.0))
    selected_period_s = 2pi * sqrt((center_inertia + mass * selected_pivot_m^2) /
                                   (mass * GRAVITY * selected_pivot_m))
    selected_inertia = mass * GRAVITY * selected_pivot_m * selected_period_s^2 /
                       (4pi^2) - mass * selected_pivot_m^2
    d_i_d_t = mass * GRAVITY * selected_pivot_m * selected_period_s / (2pi^2)
    d_i_d_h = mass * GRAVITY * selected_period_s^2 / (4pi^2) - 2mass * selected_pivot_m
    period_component = abs(d_i_d_t) * period_u_s
    pivot_component = abs(d_i_d_h) * pivot_u_m
    combined_u_inertia = hypot(period_component, pivot_component)
    residuals_ms = measured_periods_s .- [
        sqrt((fit.slope * h^2 + fit.intercept) / h) for h in pivot_distances_m
    ]
    residuals_ms .*= 1000.0
    return (;
        mass, gyration_radius_m, selected_pivot_m, center_inertia,
        pivot_distances_m, true_periods_s, measured_periods_s, x_h2_m2,
        y_t2h_s2m, fit, fitted_g, fitted_k2, fitted_radius_m,
        fitted_center_inertia, fitted_center_inertia_uncertainty,
        selected_period_s, selected_inertia,
        period_component, pivot_component, combined_u_inertia, residuals_ms,
        gravity_error_percent = 100.0 * (fitted_g - GRAVITY) / GRAVITY,
        inertia_error_percent = 100.0 * (fitted_center_inertia - center_inertia) / center_inertia,
    )
end

function pendulum_fit_figure()
    figure, controls, metrics = base_figure()
    fit_axis = Axis(
        figure[1, 1],
        title = "复摆线性化拟合",
        xlabel = "h² / m²",
        ylabel = "T²h / s²·m",
    )
    residual_axis = Axis(
        figure[1, 2],
        title = "周期拟合残差",
        xlabel = "支点距 h / m",
        ylabel = "残差 / ms",
    )

    mass = add_slider!(controls, 1, "摆体质量 m", 0.50:0.10:1.50, 1.00, value -> @sprintf("%.2f kg", value))
    radius = add_slider!(controls, 2, "回转半径 k", 8.0:0.5:16.0, 12.0, value -> @sprintf("%.1f cm", value))
    pivot = add_slider!(controls, 3, "支点距 h", 8.0:1.0:32.0, 20.0, value -> @sprintf("%.1f cm", value))
    period_u = add_slider!(controls, 4, "周期 u(T)", 1:1:15, 5, value -> @sprintf("%.0f ms", value))
    pivot_u = add_slider!(controls, 5, "支点距 u(h)", 0.1:0.1:1.0, 0.5, value -> @sprintf("%.1f mm", value))

    data = lift(mass.value, radius.value, pivot.value, period_u.value, pivot_u.value) do m, k, h, u_t, u_h
        pendulum_fit_model(Float64(m), Float64(k), Float64(h), Float64(u_t), Float64(u_h))
    end
    scatter!(fit_axis, lift(value -> value.x_h2_m2, data), lift(value -> value.y_t2h_s2m, data), color = CYAN, markersize = 12, label = "周期测量")
    lines!(fit_axis, lift(value -> value.x_h2_m2, data), lift(value -> value.fit.predicted, data), color = GREEN, linewidth = 2.7, label = "T²h=a h²+b")
    axislegend(fit_axis, position = :lt, framevisible = false)
    hlines!(residual_axis, [0.0], color = (:white, 0.3), linestyle = :dash)
    scatter!(residual_axis, lift(value -> value.pivot_distances_m, data), lift(value -> value.residuals_ms, data), color = AMBER, markersize = 13)

    values = (
        lift(value -> @sprintf("g=%.4f m/s²", value.fitted_g), data),
        lift(value -> @sprintf("I_C拟合=%.2e±%.1e", value.fitted_center_inertia, value.fitted_center_inertia_uncertainty), data),
        lift(value -> @sprintf("I(h=%.0fcm)=%.2e", value.selected_pivot_m * 100.0, value.selected_inertia), data),
        lift(value -> @sprintf("u[I(h)]=%.1e", value.combined_u_inertia), data),
    )
    detail = lift(data) do value
        @sprintf("惯量单位 kg·m²。复摆线性化 T²h=(4π²/g)(h²+k²)；I_C的u由斜率—截距协方差传播，u[I(h)]仅由选定支点 T、h 传播。g偏差 %+.3f%%，I_C偏差 %+.3f%%。", value.gravity_error_percent, value.inertia_error_percent)
    end
    add_metrics!(metrics, values, detail)
    return figure
end

function run_self_test()
    @assert isapprox(disk_inertia(0.5, 0.06), 9.0e-4; rtol = 1.0e-14)

    torsion = torsion_model(8.0, 900.0, 0.5, 6.0, 0.03)
    @assert torsion.period_s > 0.0
    @assert torsion.total_inertia > torsion.object_inertia
    @assert abs(torsion.relative_error_percent) < 0.5
    @assert length(torsion.time_s) == 360

    trifilar = trifilar_model(2.0, 12.0, 10.0, 60.0, 0.0)
    @assert trifilar.period_s > 0.0
    @assert isapprox(trifilar.measured_inertia, trifilar.true_inertia; rtol = 1.0e-13)
    @assert isapprox(
        trifilar.restoring_constant,
        trifilar.mass * GRAVITY * trifilar.upper_radius_m * trifilar.lower_radius_m /
        trifilar.vertical_spacing_m;
        rtol = 1.0e-14,
    )

    parallel = parallel_axis_model(0.5, 5.0, 6.0, 8.0, 0.0)
    @assert isapprox(parallel.fitted_mass_kg, 0.5; rtol = 1.0e-12)
    @assert isapprox(parallel.fitted_center_inertia, disk_inertia(0.5, 0.05); rtol = 1.0e-12)
    @assert parallel.fit.r_squared > 0.999999999

    pendulum = pendulum_fit_model(1.0, 12.0, 20.0, 0.0, 0.5)
    @assert isapprox(pendulum.fitted_g, GRAVITY; rtol = 1.0e-11)
    @assert isapprox(pendulum.fitted_radius_m, 0.12; rtol = 1.0e-11)
    @assert isapprox(pendulum.fitted_center_inertia, 0.0144; rtol = 1.0e-11)
    @assert pendulum.combined_u_inertia > 0.0
    @assert maximum(abs.(pendulum.residuals_ms)) < 1.0e-8
    noisy_pendulum = pendulum_fit_model(1.0, 12.0, 20.0, 5.0, 0.5)
    @assert noisy_pendulum.fitted_center_inertia_uncertainty > 0.0
    @assert noisy_pendulum.combined_u_inertia > 0.0

    for builder in (torsion_figure, trifilar_figure, parallel_axis_figure, pendulum_fit_figure)
        @assert builder() isa Figure
    end
    println("转动惯量四个独立网页实验自检通过：扭摆、三线摆、平行轴定理与复摆拟合均正常。")
end

const PAGE_STYLE = """
html, body { margin: 0; width: 100%; height: 100%; background: #0b0f14; color: #eef3f8; }
body { position: relative; overflow: hidden; font-family: 'Microsoft YaHei', 'Noto Sans CJK SC', sans-serif; }
.rotational-inertia-lab { position: absolute; left: 0; top: 0; width: $(FIGURE_WIDTH)px; height: $(FIGURE_HEIGHT)px;
    margin: 0; padding: 0; box-sizing: border-box; overflow: hidden; background: #0b0f14;
    transform-origin: 0 0; }
.rotational-inertia-diagnostic {
    position: fixed; left: 16px; right: 16px; bottom: 16px; z-index: 1002;
    display: none; padding: 10px 12px; color: #f7d7d7;
    background: rgba(64, 20, 28, .94); border: 1px solid rgba(255, 85, 105, .65);
    border-radius: 6px; font: 13px/1.5 ui-monospace, Consolas, monospace;
    white-space: pre-wrap;
}
.rotational-inertia-diagnostic.visible { display: block; }
"""

const CLIENT_STATUS_SCRIPT = """
(() => {
    let ready = false;
    const parentWindow = window.parent || window;
    const send = (type, detail = "") => {
        parentWindow.postMessage({ type, detail }, "*");
    };
    let fitFrame = 0;
    let layoutScale = 1;
    const syncWGLPointerScale = event => {
        const canvas = event && event.target instanceof HTMLCanvasElement
            ? event.target
            : null;
        const screen = canvas && canvas.wglmakie_screen;
        if (!screen || !Number.isFinite(screen.winscale) || screen.winscale <= 0) return;
        if (!Number.isFinite(screen.__physicsBaseWinscale)) {
            screen.__physicsBaseWinscale = screen.winscale;
        }
        const baseWinscale = screen.__physicsBaseWinscale;
        screen.winscale = baseWinscale * layoutScale;
        window.clearTimeout(screen.__physicsPointerScaleTimer);
        screen.__physicsPointerScaleTimer = window.setTimeout(() => {
            if (canvas.wglmakie_screen === screen) screen.winscale = baseWinscale;
        }, 120);
    };
    const fitLayout = () => {
        const page = document.querySelector(".rotational-inertia-lab");
        if (!page) return;
        const viewport = window.visualViewport;
        const viewportWidth = Math.max(
            1,
            viewport ? viewport.width : (document.documentElement.clientWidth || window.innerWidth)
        );
        const viewportHeight = Math.max(
            1,
            viewport ? viewport.height : (document.documentElement.clientHeight || window.innerHeight)
        );
        const availableWidth = Math.max(1, viewportWidth - 12);
        const availableHeight = Math.max(1, viewportHeight - 8);
        const scale = Math.min(
            1.05,
            availableWidth / $(FIGURE_WIDTH),
            availableHeight / $(FIGURE_HEIGHT)
        );
        const renderedWidth = $(FIGURE_WIDTH) * scale;
        const renderedHeight = $(FIGURE_HEIGHT) * scale;
        const viewportLeft = viewport ? viewport.offsetLeft : 0;
        const viewportTop = viewport ? viewport.offsetTop : 0;
        const offsetX = viewportLeft + Math.max(0, (viewportWidth - renderedWidth) / 2);
        const offsetY = viewportTop + Math.max(0, (viewportHeight - renderedHeight) / 2);
        layoutScale = scale;
        page.style.transform = "translate3d(" + offsetX + "px," + offsetY + "px,0) scale(" + scale + ")";
    };
    const scheduleFit = () => {
        if (fitFrame) cancelAnimationFrame(fitFrame);
        fitFrame = requestAnimationFrame(() => {
            fitFrame = 0;
            fitLayout();
        });
    };
    fitLayout();
    requestAnimationFrame(fitLayout);
    window.addEventListener("resize", scheduleFit);
    window.addEventListener("orientationchange", scheduleFit);
    if (window.visualViewport) {
        window.visualViewport.addEventListener("resize", scheduleFit);
        window.visualViewport.addEventListener("scroll", scheduleFit);
    }
    if (window.ResizeObserver) {
        const layoutObserver = new ResizeObserver(scheduleFit);
        layoutObserver.observe(document.documentElement);
        layoutObserver.observe(document.body);
    }
    setTimeout(fitLayout, 250);
    for (const eventName of [
        "mousemove", "mousedown", "mouseup", "pointerdown", "pointermove",
        "pointerup", "pointercancel", "wheel"
    ]) {
        document.addEventListener(eventName, syncWGLPointerScale, {
            capture: true,
            passive: true,
        });
    }

    const showDiagnostic = detail => {
        let box = document.getElementById("rotational-inertia-diagnostic");
        if (!box) {
            box = document.createElement("div");
            box.id = "rotational-inertia-diagnostic";
            box.className = "rotational-inertia-diagnostic";
            document.body.appendChild(box);
        }
        box.textContent = detail;
        box.classList.add("visible");
        send("rotational-inertia-wgl-failed", detail);
    };
    const webglProbe = () => {
        try {
            const canvas = document.createElement("canvas");
            if (canvas.getContext("webgl2", { antialias: true })) return "webgl2";
            if (
                canvas.getContext("webgl", { antialias: true }) ||
                canvas.getContext("experimental-webgl")
            ) return "webgl1";
        } catch (error) {
            return "error: " + error.message;
        }
        return "none";
    };
    const glStatus = webglProbe();
    if (glStatus === "none" || glStatus.startsWith("error:")) {
        showDiagnostic("浏览器无法创建 WebGL 上下文：" + glStatus);
        return;
    }
    const startedAt = performance.now();
    const check = () => {
        const canvas = document.querySelector("canvas");
        const spinner = document.querySelector(".wglmakie-spinner");
        const spinnerVisible = Boolean(
            spinner && spinner.getClientRects().length > 0 &&
            getComputedStyle(spinner).visibility !== "hidden"
        );
        if (canvas && canvas.width > 0 && canvas.height > 0 && !spinnerVisible) {
            ready = true;
            send("rotational-inertia-wgl-ready", glStatus);
            return;
        }
        if (!ready && performance.now() - startedAt > 75000) {
            showDiagnostic(
                "WGLMakie/Bonito 初始化超过 75 秒。" +
                "\\nWebGL 状态：" + glStatus +
                "\\n页面地址：" + location.href
            );
            return;
        }
        window.setTimeout(check, 300);
    };
    window.addEventListener("error", event => {
        showDiagnostic(
            "浏览器脚本错误：" + event.message +
            "\\n" + event.filename + ":" + event.lineno
        );
    });
    window.addEventListener("unhandledrejection", event => {
        showDiagnostic("浏览器 Promise 错误：" + String(event.reason));
    });
    check();
})();
"""

function experiment_app(title, builder)
    return Bonito.App(; title = title) do
        figure = builder()
        DOM.div(
            DOM.style(PAGE_STYLE),
            DOM.div(figure; class = "rotational-inertia-lab"),
            DOM.script(CLIENT_STATUS_SCRIPT),
        )
    end
end

function index_app()
    links = [
        DOM.a(name; href = path, style = "color:#73d7cf;margin-right:24px")
        for (name, path) in (
            ("扭摆周期与转动惯量", "./torsion"),
            ("三线摆几何测量", "./trifilar"),
            ("平行轴定理验证", "./parallel-axis"),
            ("复摆与不确定度拟合", "./pendulum-fit"),
        )
    ]
    return Bonito.App(
        DOM.div(
            DOM.style(PAGE_STYLE),
            DOM.h1("转动惯量测定"),
            DOM.div(links...),
            style = "padding:32px;background:#0b0f14;color:#eef3f8;min-height:100vh",
        );
        title = "转动惯量测定",
    )
end

function health_app()
    return Bonito.App(DOM.pre(HEALTH_MARKER); title = HEALTH_MARKER)
end

function main()
    load_packaged_wgl_shaders!()
    WGLMakie.activate!(; use_html_widgets = true)
    configure_theme!()
    if "--self-test" in ARGS
        run_self_test()
        return
    end
    host = get(ENV, "ROTATIONAL_INERTIA_WEB_HOST", "127.0.0.1")
    port = parse(Int, get(ENV, "ROTATIONAL_INERTIA_WEB_PORT", "9391"))
    proxy_url = strip(get(ENV, "ROTATIONAL_INERTIA_WEB_PROXY_URL", "."))
    isempty(proxy_url) && (proxy_url = ".")
    server = Bonito.Server(host, port; proxy_url = proxy_url)
    Bonito.route!(server, "/__physics_health__" => health_app())
    Bonito.route!(server, "/" => index_app())
    Bonito.route!(server, "/torsion" => experiment_app("扭摆周期与转动惯量", torsion_figure))
    Bonito.route!(server, "/trifilar" => experiment_app("三线摆几何测量", trifilar_figure))
    Bonito.route!(server, "/parallel-axis" => experiment_app("平行轴定理验证", parallel_axis_figure))
    Bonito.route!(server, "/pendulum-fit" => experiment_app("复摆与不确定度拟合", pendulum_fit_figure))
    println("转动惯量网页实验已启动：http://$(host):$(port)")
    wait(server)
end

if abspath(PROGRAM_FILE) == @__FILE__
    main()
end
