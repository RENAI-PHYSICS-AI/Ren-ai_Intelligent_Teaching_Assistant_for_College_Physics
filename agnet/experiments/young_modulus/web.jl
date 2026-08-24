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
const DEFAULT_YOUNG_MODULUS_PA = 2.00e11
const DEFAULT_WIRE_LENGTH_M = 0.800
const DEFAULT_WIRE_DIAMETER_MM = 0.500
const DEFAULT_LEVER_ARM_MM = 80.0
const DEFAULT_SCALE_DISTANCE_M = 1.500
const LOAD_MASSES_KG = collect(0.0:1.0:6.0)

const FIGURE_WIDTH = 960
const FIGURE_HEIGHT = 760

const CYAN = RGBf(0.18, 0.78, 0.92)
const PINK = RGBf(0.94, 0.35, 0.50)
const AMBER = RGBf(1.00, 0.72, 0.24)
const GREEN = RGBf(0.36, 0.82, 0.55)
const VIOLET = RGBf(0.61, 0.48, 0.92)
const MUTED = RGBf(0.58, 0.62, 0.70)
const PANEL_BG = RGBf(0.075, 0.085, 0.105)
const CJK_PROBE_TEXT = "杨氏模量静态拉伸光杠杆加卸载拟合不确定度"
const HEALTH_MARKER = "physics-experiment:young-modulus"
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
    asset_dir = normpath(
        joinpath(Sys.BINDIR, "..", "share", "photoelectric", "wglmakie_assets"),
    )
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
        candidates = [
            String(strip(line))
            for line in split(output, '\n')
            if !isempty(strip(line))
        ]
        return isempty(candidates) ? nothing : first_cjk_font(candidates)
    catch
        return nothing
    end
end

function cjk_font_family()
    runtime_font = normpath(
        joinpath(LAB_DIR, "..", "..", "..", ".runtime", "fonts", "NotoSansCJKsc-Regular.otf"),
    )
    bundled_font = normpath(
        joinpath(LAB_DIR, "..", "..", "assets", "fonts", "NotoSansCJKsc-Regular.otf"),
    )
    julia_font = normpath(
        joinpath(
            Sys.BINDIR,
            "..",
            "share",
            "photoelectric",
            "fonts",
            "NotoSansCJKsc-Regular.otf",
        ),
    )
    regular = first_cjk_font([
        get(ENV, "PHYSICS_CJK_FONT", ""),
        runtime_font,
        bundled_font,
        julia_font,
        isempty(get(ENV, "WINDIR", "")) ? "" : joinpath(ENV["WINDIR"], "Fonts", "msyh.ttc"),
        "/System/Library/Fonts/PingFang.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/google-noto-cjk-fonts/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/google-noto-vf/NotoSansCJK-VF.ttf",
        fontconfig_match("Noto Sans CJK SC:lang=zh-cn"),
    ])
    isnothing(regular) && error(
        "未找到真正包含中文字形的字体。请通过 PHYSICS_CJK_FONT 指定 Noto Sans CJK SC 字体文件。",
    )
    bold = first_cjk_font([
        get(ENV, "PHYSICS_CJK_FONT", ""),
        runtime_font,
        bundled_font,
        julia_font,
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
    set_theme!(
        Theme(
            fontsize = 14,
            font = fonts.regular,
            fonts = (; regular = fonts.regular, bold = fonts.bold),
            textcolor = :white,
            backgroundcolor = RGBf(0.045, 0.052, 0.065),
            Axis = (
                backgroundcolor = PANEL_BG,
                xgridcolor = (:white, 0.07),
                ygridcolor = (:white, 0.07),
                spinecolor = (:white, 0.18),
                xtickcolor = (:white, 0.25),
                ytickcolor = (:white, 0.25),
                topspinevisible = false,
                rightspinevisible = false,
            ),
        ),
    )
end

function base_figure()
    configure_theme!()
    figure = Figure(
        size = (FIGURE_WIDTH, FIGURE_HEIGHT),
        figure_padding = (18, 18, 22, 32),
    )
    controls = GridLayout()
    metrics = GridLayout()
    figure[2, 1:2] = controls
    figure[3, 1:2] = metrics
    rowsize!(figure.layout, 1, 380)
    # Five uncertainty sliders occupy 136 px including gaps.  Keeping this
    # row at 140 px moves the metric/detail block fully inside the 760 px
    # canvas instead of letting its last line fall below the bottom edge.
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
    slider = Slider(
        grid[row, 2],
        range = range,
        startvalue = startvalue,
        update_while_dragging = false,
    )
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
    Label(
        grid[2, 1:4],
        detail,
        color = MUTED,
        halign = :left,
        fontsize = 12.5,
        tellwidth = false,
    )
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
    total_variation = sum(abs2, yf .- ybar)
    r_squared = total_variation > 0 ? 1.0 - sum(abs2, residuals) / total_variation : 1.0
    return (; slope, intercept, predicted, residuals, slope_uncertainty, r_squared)
end

wire_area_m2(diameter_mm) = pi * (Float64(diameter_mm) * 1.0e-3)^2 / 4.0

function elongation_m(force_n, length_m, young_modulus_pa, diameter_mm)
    area = wire_area_m2(diameter_mm)
    Float64(young_modulus_pa) > 0 || throw(ArgumentError("杨氏模量必须大于零"))
    Float64(length_m) > 0 || throw(ArgumentError("金属丝长度必须大于零"))
    area > 0 || throw(ArgumentError("金属丝直径必须大于零"))
    return Float64(force_n) * Float64(length_m) / (area * Float64(young_modulus_pa))
end

function optical_shift_m(delta_length_m, lever_arm_mm, scale_distance_m)
    lever_arm_m = Float64(lever_arm_mm) * 1.0e-3
    lever_arm_m > 0 || throw(ArgumentError("光杠杆臂长必须大于零"))
    Float64(scale_distance_m) > 0 || throw(ArgumentError("镜尺距离必须大于零"))
    theta = atan(Float64(delta_length_m) / lever_arm_m)
    return Float64(scale_distance_m) * tan(2.0 * theta)
end

function inverse_optical_elongation_m(scale_shift_m, lever_arm_mm, scale_distance_m)
    lever_arm_m = Float64(lever_arm_mm) * 1.0e-3
    lever_arm_m > 0 || throw(ArgumentError("光杠杆臂长必须大于零"))
    Float64(scale_distance_m) > 0 || throw(ArgumentError("镜尺距离必须大于零"))
    theta = 0.5 * atan(Float64(scale_shift_m) / Float64(scale_distance_m))
    return lever_arm_m * tan(theta)
end

function small_angle_elongation_m(scale_shift_m, lever_arm_mm, scale_distance_m)
    return Float64(lever_arm_mm) * 1.0e-3 * Float64(scale_shift_m) /
           (2.0 * Float64(scale_distance_m))
end

function principle_model(delta_length_um, lever_arm_mm, scale_distance_m, display_range_um)
    delta_m = Float64(delta_length_um) * 1.0e-6
    arm_mm = Float64(lever_arm_mm)
    distance_m = Float64(scale_distance_m)
    scale_shift_m = optical_shift_m(delta_m, arm_mm, distance_m)
    approximate_shift_m = 2.0 * distance_m * delta_m / (arm_mm * 1.0e-3)
    theta_rad = atan(delta_m / (arm_mm * 1.0e-3))
    range_um = Float64(display_range_um)
    elongations_um = collect(range(0.0, range_um; length = 180))
    exact_shifts_mm = [
        optical_shift_m(value * 1.0e-6, arm_mm, distance_m) * 1000.0
        for value in elongations_um
    ]
    approximate_shifts_mm = [
        2.0 * distance_m * value * 1.0e-6 / (arm_mm * 1.0e-3) * 1000.0
        for value in elongations_um
    ]
    schematic_shift = clamp(scale_shift_m * 1000.0 / 28.0, 0.0, 0.58)
    return (;
        delta_m,
        arm_mm,
        distance_m,
        scale_shift_m,
        approximate_shift_m,
        theta_rad,
        elongations_um,
        exact_shifts_mm,
        approximate_shifts_mm,
        selected_um = Float64(delta_length_um),
        selected_shift_mm = scale_shift_m * 1000.0,
        schematic_shift,
        amplification = 2.0 * distance_m / (arm_mm * 1.0e-3),
        approximation_error_percent = scale_shift_m == 0 ? 0.0 :
            100.0 * (approximate_shift_m - scale_shift_m) / scale_shift_m,
    )
end

function principle_figure()
    figure, controls, metrics = base_figure()
    schematic_axis = Axis(
        figure[1, 1],
        title = "光杠杆几何放大",
        xlabel = "光路示意（纵向位移已放大）",
        ylabel = "相对高度",
    )
    relation_axis = Axis(
        figure[1, 2],
        title = "标尺位移与金属丝伸长量",
        xlabel = "伸长量 ΔL / μm",
        ylabel = "标尺位移 Δs / mm",
    )
    limits!(schematic_axis, 0.0, 1.05, -0.12, 1.10)

    delta_length = add_slider!(controls, 1, "伸长量 ΔL", 0:5:250, 100, value -> @sprintf("%.0f μm", value))
    lever_arm = add_slider!(controls, 2, "光杠杆臂长 b", 50:5:120, 80, value -> @sprintf("%.0f mm", value))
    scale_distance = add_slider!(controls, 3, "镜尺距离 D", 0.8:0.1:2.2, 1.5, value -> @sprintf("%.1f m", value))
    display_range = add_slider!(controls, 4, "曲线范围", 100:25:400, 250, value -> @sprintf("%.0f μm", value))

    data = lift(
        delta_length.value,
        lever_arm.value,
        scale_distance.value,
        display_range.value,
    ) do delta, arm, distance, range_um
        principle_model(Float64(delta), Float64(arm), Float64(distance), Float64(range_um))
    end

    lines!(schematic_axis, [0.10, 0.45], [0.05, 0.05], color = MUTED, linewidth = 6, label = "光杠杆底座")
    scatter!(schematic_axis, [0.10, 0.45], [0.05, 0.05], color = AMBER, markersize = 15)
    lines!(schematic_axis, [0.28, 0.28], [0.05, 0.68], color = GREEN, linewidth = 7, label = "平面镜")
    lines!(schematic_axis, [0.28, 0.98], [0.55, 0.55], color = (:white, 0.25), linestyle = :dash)
    lines!(
        schematic_axis,
        lift(value -> [0.98, 0.28], data),
        lift(value -> [0.28, 0.55], data),
        color = CYAN,
        linewidth = 2.5,
        label = "入射光",
    )
    lines!(
        schematic_axis,
        lift(value -> [0.28, 0.98], data),
        lift(value -> [0.55, 0.55 + value.schematic_shift], data),
        color = PINK,
        linewidth = 2.8,
        label = "反射光",
    )
    lines!(schematic_axis, [0.98, 0.98], [0.15, 1.03], color = AMBER, linewidth = 5, label = "标尺")
    scatter!(
        schematic_axis,
        lift(value -> [0.98], data),
        lift(value -> [0.55 + value.schematic_shift], data),
        color = PINK,
        markersize = 15,
    )
    axislegend(schematic_axis, position = :lt, framevisible = false, labelsize = 10)

    lines!(relation_axis, lift(value -> value.elongations_um, data), lift(value -> value.exact_shifts_mm, data), color = CYAN, linewidth = 2.6, label = "精确几何")
    lines!(relation_axis, lift(value -> value.elongations_um, data), lift(value -> value.approximate_shifts_mm, data), color = AMBER, linewidth = 2.0, linestyle = :dash, label = "小角近似")
    scatter!(relation_axis, lift(value -> [value.selected_um], data), lift(value -> [value.selected_shift_mm], data), color = PINK, markersize = 16, label = "当前状态")
    axislegend(relation_axis, position = :lt, framevisible = false, labelsize = 10)

    values = (
        lift(value -> @sprintf("θ = %.3f mrad", value.theta_rad * 1000.0), data),
        lift(value -> @sprintf("2θ = %.3f mrad", 2.0 * value.theta_rad * 1000.0), data),
        lift(value -> @sprintf("Δs = %.3f mm", value.selected_shift_mm), data),
        lift(value -> @sprintf("放大倍数 ≈ %.1f", value.amplification), data),
    )
    detail = lift(data) do value
        @sprintf(
            "镜面转角 tanθ=ΔL/b，反射光偏转 2θ；小角度下 ΔL=bΔs/(2D)。当前近似误差 %+.4f%%。",
            value.approximation_error_percent,
        )
    end
    add_metrics!(metrics, values, detail)
    return figure
end

function loading_model(
    young_modulus_gpa,
    reading_noise_mm,
    hysteresis_mm,
    selected_mass_kg;
    length_m = DEFAULT_WIRE_LENGTH_M,
    diameter_mm = DEFAULT_WIRE_DIAMETER_MM,
    lever_arm_mm = DEFAULT_LEVER_ARM_MM,
    scale_distance_m = DEFAULT_SCALE_DISTANCE_M,
)
    modulus_pa = Float64(young_modulus_gpa) * 1.0e9
    noise_mm = Float64(reading_noise_mm)
    lag_mm = Float64(hysteresis_mm)
    masses_kg = copy(LOAD_MASSES_KG)
    forces_n = masses_kg .* GRAVITY
    elongations_m = [
        elongation_m(force, length_m, modulus_pa, diameter_mm)
        for force in forces_n
    ]
    ideal_shifts_mm = [
        optical_shift_m(delta, lever_arm_mm, scale_distance_m) * 1000.0
        for delta in elongations_m
    ]
    base_reading_mm = 500.0
    maximum_mass = maximum(masses_kg)
    loading_readings_mm = Float64[]
    unloading_readings_mm = Float64[]
    for (index, (mass, shift)) in enumerate(zip(masses_kg, ideal_shifts_mm))
        loading_error = noise_mm * (0.62 * sin(1.07 * index) + 0.21 * cos(0.73 * index))
        unloading_error = noise_mm * (0.55 * cos(0.91 * index) - 0.18 * sin(0.66 * index))
        elastic_lag = lag_mm * (1.0 - mass / maximum_mass)
        push!(loading_readings_mm, base_reading_mm + shift + loading_error)
        push!(unloading_readings_mm, base_reading_mm + shift + unloading_error + elastic_lag)
    end
    average_readings_mm = (loading_readings_mm .+ unloading_readings_mm) ./ 2.0
    net_shifts_mm = average_readings_mm .- average_readings_mm[1]
    measured_elongations_mm = [
        small_angle_elongation_m(shift / 1000.0, lever_arm_mm, scale_distance_m) * 1000.0
        for shift in net_shifts_mm
    ]
    selected_mass = Float64(selected_mass_kg)
    selected_index = findfirst(value -> isapprox(value, selected_mass; atol = 1.0e-10), masses_kg)
    isnothing(selected_index) && throw(ArgumentError("所选砝码质量不在加卸载序列中"))
    return (;
        modulus_pa,
        masses_kg,
        forces_n,
        elongations_m,
        ideal_shifts_mm,
        loading_readings_mm,
        unloading_readings_mm,
        average_readings_mm,
        net_shifts_mm,
        measured_elongations_mm,
        selected_mass,
        selected_force_n = forces_n[selected_index],
        selected_loading_mm = loading_readings_mm[selected_index],
        selected_unloading_mm = unloading_readings_mm[selected_index],
        selected_average_mm = average_readings_mm[selected_index],
        selected_elongation_mm = measured_elongations_mm[selected_index],
        maximum_loading_difference_mm = maximum(abs.(loading_readings_mm .- unloading_readings_mm)),
    )
end

function loading_figure()
    figure, controls, metrics = base_figure()
    reading_axis = Axis(
        figure[1, 1],
        title = "加、卸载标尺读数",
        xlabel = "载荷 F / N",
        ylabel = "标尺读数 s / mm",
    )
    elongation_axis = Axis(
        figure[1, 2],
        title = "平均读数换算伸长量",
        xlabel = "载荷 F / N",
        ylabel = "伸长量 ΔL / mm",
    )

    modulus = add_slider!(controls, 1, "材料 E", 160:5:240, 200, value -> @sprintf("%.0f GPa", value))
    reading_noise = add_slider!(controls, 2, "读数散布", 0.00:0.02:0.30, 0.10, value -> @sprintf("%.2f mm", value))
    hysteresis = add_slider!(controls, 3, "加卸载回差", 0.00:0.02:0.30, 0.08, value -> @sprintf("%.2f mm", value))
    selected_mass = add_slider!(controls, 4, "查看砝码质量", LOAD_MASSES_KG, 3.0, value -> @sprintf("%.0f kg", value))

    data = lift(
        modulus.value,
        reading_noise.value,
        hysteresis.value,
        selected_mass.value,
    ) do e_gpa, noise, lag, mass
        loading_model(Float64(e_gpa), Float64(noise), Float64(lag), Float64(mass))
    end

    lines!(reading_axis, lift(value -> value.forces_n, data), lift(value -> value.loading_readings_mm, data), color = CYAN, linewidth = 2.4, label = "逐级加砝码")
    scatter!(reading_axis, lift(value -> value.forces_n, data), lift(value -> value.loading_readings_mm, data), color = CYAN, markersize = 11)
    lines!(reading_axis, lift(value -> value.forces_n, data), lift(value -> value.unloading_readings_mm, data), color = AMBER, linewidth = 2.4, label = "逐级减砝码")
    scatter!(reading_axis, lift(value -> value.forces_n, data), lift(value -> value.unloading_readings_mm, data), color = AMBER, markersize = 11)
    scatter!(reading_axis, lift(value -> [value.selected_force_n], data), lift(value -> [value.selected_average_mm], data), color = PINK, markersize = 18, label = "当前平均")
    axislegend(reading_axis, position = :lt, framevisible = false, labelsize = 10)

    lines!(elongation_axis, lift(value -> value.forces_n, data), lift(value -> value.measured_elongations_mm, data), color = GREEN, linewidth = 2.5, label = "由平均读数换算")
    scatter!(elongation_axis, lift(value -> value.forces_n, data), lift(value -> value.measured_elongations_mm, data), color = GREEN, markersize = 11)
    lines!(elongation_axis, lift(value -> value.forces_n, data), lift(value -> value.elongations_m .* 1000.0, data), color = VIOLET, linewidth = 2.0, linestyle = :dash, label = "理想弹性伸长")
    axislegend(elongation_axis, position = :lt, framevisible = false, labelsize = 10)

    values = (
        lift(value -> @sprintf("F = %.3f N", value.selected_force_n), data),
        lift(value -> @sprintf("加读数 %.3f mm", value.selected_loading_mm), data),
        lift(value -> @sprintf("卸读数 %.3f mm", value.selected_unloading_mm), data),
        lift(value -> @sprintf("ΔL = %.4f mm", value.selected_elongation_mm), data),
    )
    detail = lift(data) do value
        @sprintf(
            "从 0 kg 逐级加至 6 kg，再逐级卸载；同一载荷取加、卸载读数平均值并以零载荷调零。最大加卸载差 %.3f mm。",
            value.maximum_loading_difference_mm,
        )
    end
    add_metrics!(metrics, values, detail)
    return figure
end

function fit_model(young_modulus_gpa, length_m, diameter_mm, reading_noise_mm)
    loading = loading_model(
        young_modulus_gpa,
        reading_noise_mm,
        0.08,
        3.0;
        length_m = Float64(length_m),
        diameter_mm = Float64(diameter_mm),
    )
    fit = linear_fit(loading.measured_elongations_mm, loading.forces_n)
    area = wire_area_m2(diameter_mm)
    slope_n_per_m = fit.slope * 1000.0
    modulus_fit_pa = slope_n_per_m * Float64(length_m) / area
    modulus_slope_uncertainty_pa = fit.slope_uncertainty * 1000.0 * Float64(length_m) / area
    return (;
        loading,
        fit,
        length_m = Float64(length_m),
        diameter_mm = Float64(diameter_mm),
        area,
        modulus_fit_pa,
        modulus_slope_uncertainty_pa,
        residuals_mn = fit.residuals .* 1000.0,
        relative_error_percent = 100.0 * (modulus_fit_pa - loading.modulus_pa) / loading.modulus_pa,
    )
end

function fit_figure()
    figure, controls, metrics = base_figure()
    fit_axis = Axis(
        figure[1, 1],
        title = "F-ΔL 自由截距线性拟合",
        xlabel = "伸长量 ΔL / mm",
        ylabel = "拉力 F / N",
    )
    residual_axis = Axis(
        figure[1, 2],
        title = "拟合残差",
        xlabel = "拉力 F / N",
        ylabel = "残差 / mN",
    )

    modulus = add_slider!(controls, 1, "真实 E", 160:5:240, 200, value -> @sprintf("%.0f GPa", value))
    wire_length = add_slider!(controls, 2, "金属丝长度 L", 0.50:0.05:1.20, 0.80, value -> @sprintf("%.2f m", value))
    wire_diameter = add_slider!(controls, 3, "金属丝直径 d", 0.40:0.02:0.70, 0.50, value -> @sprintf("%.2f mm", value))
    reading_noise = add_slider!(controls, 4, "标尺读数散布", 0.00:0.02:0.30, 0.10, value -> @sprintf("%.2f mm", value))

    data = lift(
        modulus.value,
        wire_length.value,
        wire_diameter.value,
        reading_noise.value,
    ) do e_gpa, length, diameter, noise
        fit_model(Float64(e_gpa), Float64(length), Float64(diameter), Float64(noise))
    end

    scatter!(fit_axis, lift(value -> value.loading.measured_elongations_mm, data), lift(value -> value.loading.forces_n, data), color = CYAN, markersize = 13, label = "平均测量值")
    lines!(fit_axis, lift(value -> value.loading.measured_elongations_mm, data), lift(value -> value.fit.predicted, data), color = GREEN, linewidth = 2.7, label = "F=kΔL+F₀")
    axislegend(fit_axis, position = :lt, framevisible = false)
    hlines!(residual_axis, [0.0], color = (:white, 0.35), linestyle = :dash)
    scatter!(residual_axis, lift(value -> value.loading.forces_n, data), lift(value -> value.residuals_mn, data), color = AMBER, markersize = 13)

    values = (
        lift(value -> @sprintf("k = %.3f N/mm", value.fit.slope), data),
        lift(value -> @sprintf("F₀ = %+.3f N", value.fit.intercept), data),
        lift(value -> @sprintf("E拟合 = %.2f GPa", value.modulus_fit_pa / 1.0e9), data),
        lift(value -> @sprintf("R² = %.6f", value.fit.r_squared), data),
    )
    detail = lift(data) do value
        @sprintf(
            "A=πd²/4，F=kΔL+F₀，E=kL/A；截距不强制为零。斜率标准不确定度对应 u(E)=%.3f GPa，相对偏差 %+.3f%%。",
            value.modulus_slope_uncertainty_pa / 1.0e9,
            value.relative_error_percent,
        )
    end
    add_metrics!(metrics, values, detail)
    return figure
end

function uncertainty_model(
    scale_reading_uncertainty_mm,
    diameter_uncertainty_mm,
    length_uncertainty_mm,
    lever_uncertainty_mm,
    distance_uncertainty_mm;
    young_modulus_pa = DEFAULT_YOUNG_MODULUS_PA,
    length_m = DEFAULT_WIRE_LENGTH_M,
    diameter_mm = DEFAULT_WIRE_DIAMETER_MM,
    lever_arm_mm = DEFAULT_LEVER_ARM_MM,
    scale_distance_m = DEFAULT_SCALE_DISTANCE_M,
)
    maximum_mass_kg = maximum(LOAD_MASSES_KG)
    force_n = maximum_mass_kg * GRAVITY
    delta_true_m = elongation_m(force_n, length_m, young_modulus_pa, diameter_mm)
    scale_shift_m = optical_shift_m(delta_true_m, lever_arm_mm, scale_distance_m)
    delta_measured_m = small_angle_elongation_m(scale_shift_m, lever_arm_mm, scale_distance_m)
    area = wire_area_m2(diameter_mm)
    modulus_measured_pa = force_n * length_m / (area * delta_measured_m)

    mass_uncertainty_kg = 0.0005
    force_relative = mass_uncertainty_kg / maximum_mass_kg
    length_relative = Float64(length_uncertainty_mm) * 1.0e-3 / length_m
    distance_relative = Float64(distance_uncertainty_mm) * 1.0e-3 / scale_distance_m
    diameter_relative = 2.0 * Float64(diameter_uncertainty_mm) / diameter_mm
    lever_relative = Float64(lever_uncertainty_mm) / lever_arm_mm
    scale_relative = sqrt(2.0) * Float64(scale_reading_uncertainty_mm) /
                     (scale_shift_m * 1000.0)
    component_labels = ["砝码 F", "丝长 L", "镜尺距 D", "直径 d（×2）", "杠杆臂 b", "标尺差 Δs"]
    component_relative = [
        force_relative,
        length_relative,
        distance_relative,
        diameter_relative,
        lever_relative,
        scale_relative,
    ]
    combined_relative = sqrt(sum(abs2, component_relative))
    combined_uncertainty_pa = modulus_measured_pa * combined_relative
    contribution_percent = 100.0 .* component_relative
    return (;
        force_n,
        delta_true_m,
        scale_shift_m,
        delta_measured_m,
        modulus_measured_pa,
        component_labels,
        component_indices = collect(1:length(component_labels)),
        component_relative,
        contribution_percent,
        combined_relative,
        combined_uncertainty_pa,
        lower_gpa = (modulus_measured_pa - combined_uncertainty_pa) / 1.0e9,
        center_gpa = modulus_measured_pa / 1.0e9,
        upper_gpa = (modulus_measured_pa + combined_uncertainty_pa) / 1.0e9,
    )
end

function uncertainty_figure()
    figure, controls, metrics = base_figure()
    budget_axis = Axis(
        figure[1, 1],
        title = "相对标准不确定度分量",
        xlabel = "输入量",
        ylabel = "相对分量 / %",
        xticks = (collect(1:6), ["F", "L", "D", "2u(d)/d", "b", "Δs"]),
    )
    interval_axis = Axis(
        figure[1, 2],
        title = "E 的合成标准不确定度区间",
        xlabel = "计算结果",
        ylabel = "杨氏模量 E / GPa",
        xticks = ([1.0], ["E ± u(E)"]),
    )
    xlims!(interval_axis, 0.5, 1.5)

    scale_u = add_slider!(controls, 1, "标尺读数 u(s)", 0.02:0.01:0.20, 0.10, value -> @sprintf("%.2f mm", value))
    diameter_u = add_slider!(controls, 2, "直径 u(d)", 0.001:0.001:0.010, 0.005, value -> @sprintf("%.3f mm", value))
    length_u = add_slider!(controls, 3, "丝长 u(L)", 0.5:0.5:5.0, 1.0, value -> @sprintf("%.1f mm", value))
    lever_u = add_slider!(controls, 4, "杠杆臂 u(b)", 0.05:0.05:0.50, 0.10, value -> @sprintf("%.2f mm", value))
    distance_u = add_slider!(controls, 5, "镜尺距 u(D)", 0.5:0.5:5.0, 1.0, value -> @sprintf("%.1f mm", value))

    data = lift(
        scale_u.value,
        diameter_u.value,
        length_u.value,
        lever_u.value,
        distance_u.value,
    ) do u_scale, u_diameter, u_length, u_lever, u_distance
        uncertainty_model(
            Float64(u_scale),
            Float64(u_diameter),
            Float64(u_length),
            Float64(u_lever),
            Float64(u_distance),
        )
    end

    barplot!(budget_axis, lift(value -> value.component_indices, data), lift(value -> value.contribution_percent, data), color = [CYAN, GREEN, VIOLET, PINK, AMBER, MUTED])
    lines!(interval_axis, [1.0, 1.0], lift(value -> [value.lower_gpa, value.upper_gpa], data), color = CYAN, linewidth = 7)
    scatter!(interval_axis, [1.0], lift(value -> [value.center_gpa], data), color = PINK, markersize = 19)
    hlines!(interval_axis, [DEFAULT_YOUNG_MODULUS_PA / 1.0e9], color = AMBER, linestyle = :dash, linewidth = 2.0, label = "设定真值")
    axislegend(interval_axis, position = :lt, framevisible = false)

    values = (
        lift(value -> @sprintf("E = %.2f GPa", value.center_gpa), data),
        lift(value -> @sprintf("uᵣ(E)=%.3f%%", value.combined_relative * 100.0), data),
        lift(value -> @sprintf("u(E)=%.2f GPa", value.combined_uncertainty_pa / 1.0e9), data),
        lift(value -> @sprintf("Δs = %.2f mm", value.scale_shift_m * 1000.0), data),
    )
    detail = "E=8MgLD/(πd²bΔs)；按独立输入量作平方和合成，直径项因 d² 产生系数 2。图示为标准不确定度（k=1），不替代原始重复测量的 A 类评定。"
    add_metrics!(metrics, values, detail)
    return figure
end

function run_self_test()
    @assert isapprox(wire_area_m2(0.5), pi * (0.5e-3)^2 / 4.0; rtol = 1.0e-14)
    force_n = 3.0 * GRAVITY
    delta_m = elongation_m(force_n, 0.8, 2.0e11, 0.5)
    @assert delta_m > 0
    shift_m = optical_shift_m(delta_m, 80.0, 1.5)
    @assert isapprox(inverse_optical_elongation_m(shift_m, 80.0, 1.5), delta_m; rtol = 1.0e-12)
    @assert abs(small_angle_elongation_m(shift_m, 80.0, 1.5) - delta_m) / delta_m < 0.001

    principle = principle_model(100.0, 80.0, 1.5, 250.0)
    @assert length(principle.elongations_um) == 180
    @assert principle.selected_shift_mm > 0
    @assert principle.amplification == 37.5

    loading = loading_model(200.0, 0.0, 0.0, 3.0)
    @assert loading.masses_kg == LOAD_MASSES_KG
    @assert all(diff(loading.ideal_shifts_mm) .> 0.0)
    @assert loading.selected_force_n == 3.0 * GRAVITY
    @assert loading.selected_elongation_mm > 0

    fit = fit_model(200.0, 0.8, 0.5, 0.0)
    @assert fit.fit.slope > 0
    @assert fit.fit.r_squared > 0.999999
    @assert abs(fit.modulus_fit_pa - 2.0e11) / 2.0e11 < 0.001

    uncertainty = uncertainty_model(0.10, 0.005, 1.0, 0.10, 1.0)
    @assert uncertainty.combined_relative > 0
    @assert uncertainty.combined_uncertainty_pa > 0
    @assert isapprox(uncertainty.component_relative[4], 0.02; atol = 1.0e-14)
    @assert uncertainty.lower_gpa < uncertainty.center_gpa < uncertainty.upper_gpa

    for builder in (
        principle_figure,
        loading_figure,
        fit_figure,
        uncertainty_figure,
    )
        @assert builder() isa Figure
    end
    println("杨氏模量四个独立网页实验自检通过：光杠杆原理、加卸载读数、F-ΔL拟合与不确定度均正常。")
end

const PAGE_STYLE = """
html, body { margin: 0; width: 100%; height: 100%; background: #0b0f14; color: #eef3f8; }
body { position: relative; overflow: hidden; font-family: 'Microsoft YaHei', 'Noto Sans CJK SC', sans-serif; }
.young-modulus-lab { position: absolute; left: 0; top: 0; width: $(FIGURE_WIDTH)px; height: $(FIGURE_HEIGHT)px;
    margin: 0; padding: 0; box-sizing: border-box; overflow: hidden; background: #0b0f14;
    transform-origin: 0 0; }
.young-modulus-diagnostic {
    position: fixed; left: 16px; right: 16px; bottom: 16px; z-index: 1002;
    display: none; padding: 10px 12px; color: #f7d7d7;
    background: rgba(64, 20, 28, .94); border: 1px solid rgba(255, 85, 105, .65);
    border-radius: 6px; font: 13px/1.5 ui-monospace, Consolas, monospace;
    white-space: pre-wrap;
}
.young-modulus-diagnostic.visible { display: block; }
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
        const page = document.querySelector(".young-modulus-lab");
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
        let box = document.getElementById("young-modulus-diagnostic");
        if (!box) {
            box = document.createElement("div");
            box.id = "young-modulus-diagnostic";
            box.className = "young-modulus-diagnostic";
            document.body.appendChild(box);
        }
        box.textContent = detail;
        box.classList.add("visible");
        send("young-modulus-wgl-failed", detail);
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
            spinner &&
            spinner.getClientRects().length > 0 &&
            getComputedStyle(spinner).visibility !== "hidden"
        );
        if (canvas && canvas.width > 0 && canvas.height > 0 && !spinnerVisible) {
            ready = true;
            send("young-modulus-wgl-ready", glStatus);
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
            DOM.div(figure; class = "young-modulus-lab"),
            DOM.script(CLIENT_STATUS_SCRIPT),
        )
    end
end

function index_app()
    links = [
        DOM.a(name; href = path, style = "color:#73d7cf;margin-right:24px")
        for (name, path) in (
            ("光杠杆放大原理", "./principle"),
            ("加卸载读数", "./loading"),
            ("F-ΔL线性拟合", "./fit"),
            ("E与不确定度", "./uncertainty"),
        )
    ]
    return Bonito.App(
        DOM.div(
            DOM.style(PAGE_STYLE),
            DOM.h1("杨氏模量测定（静态拉伸与光杠杆法）"),
            DOM.div(links...),
            style = "padding:32px;background:#0b0f14;color:#eef3f8;min-height:100vh",
        );
        title = "杨氏模量测定（静态拉伸与光杠杆法）",
    )
end

function health_app()
    return Bonito.App(
        DOM.pre(HEALTH_MARKER);
        title = HEALTH_MARKER,
    )
end

function main()
    load_packaged_wgl_shaders!()
    WGLMakie.activate!(; use_html_widgets = true)
    configure_theme!()
    if "--self-test" in ARGS
        run_self_test()
        return
    end
    host = get(ENV, "YOUNG_MODULUS_WEB_HOST", "127.0.0.1")
    port = parse(Int, get(ENV, "YOUNG_MODULUS_WEB_PORT", "9390"))
    proxy_url = strip(get(ENV, "YOUNG_MODULUS_WEB_PROXY_URL", "."))
    isempty(proxy_url) && (proxy_url = ".")
    server = Bonito.Server(host, port; proxy_url = proxy_url)
    Bonito.route!(server, "/__physics_health__" => health_app())
    Bonito.route!(server, "/" => index_app())
    Bonito.route!(server, "/principle" => experiment_app("光杠杆放大原理", principle_figure))
    Bonito.route!(server, "/loading" => experiment_app("加卸载读数", loading_figure))
    Bonito.route!(server, "/fit" => experiment_app("F-ΔL线性拟合", fit_figure))
    Bonito.route!(server, "/uncertainty" => experiment_app("E计算与不确定度", uncertainty_figure))
    println("杨氏模量网页实验已启动：http://$(host):$(port)")
    wait(server)
end

if abspath(PROGRAM_FILE) == @__FILE__
    main()
end
