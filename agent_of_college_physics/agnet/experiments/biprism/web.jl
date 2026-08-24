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

# Sodium D-line vacuum wavelengths and the nominal value used by the teaching
# experiment.  The unknown wavelength is never exposed as a UI control: all
# simulated readings are generated from this fixed sodium source.
const SODIUM_D2_NM = 588.9950
const SODIUM_D1_NM = 589.5924
const SODIUM_REFERENCE_NM = 589.3
const SODIUM_D2_WEIGHT = 2.0 / 3.0
const SODIUM_D1_WEIGHT = 1.0 / 3.0

const DEFAULT_SLIT_DISTANCE_M = 0.10
const DEFAULT_REFRACTIVE_INDEX = 1.515
const DEFAULT_PRISM_ANGLE_DEGREE = 0.50
const DEFAULT_SCREEN_DISTANCE_M = 0.90
const DEFAULT_LENS_FOCAL_LENGTH_M = 0.20
const DEFAULT_SOURCE_SEPARATION_MM = 2.0 * DEFAULT_SLIT_DISTANCE_M *
    (DEFAULT_REFRACTIVE_INDEX - 1.0) * deg2rad(DEFAULT_PRISM_ANGLE_DEGREE) * 1000.0

const FIGURE_WIDTH = 960
const FIGURE_HEIGHT = 760

const CYAN = RGBf(0.18, 0.78, 0.92)
const PINK = RGBf(0.94, 0.35, 0.50)
const AMBER = RGBf(1.00, 0.72, 0.24)
const GREEN = RGBf(0.36, 0.82, 0.55)
const VIOLET = RGBf(0.61, 0.48, 0.92)
const MUTED = RGBf(0.58, 0.62, 0.70)
const PANEL_BG = RGBf(0.075, 0.085, 0.105)
const CJK_PROBE_TEXT = "双棱镜干涉测量钠黄光波长"
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
    # The portable runtime already packages these assets for photoelectric.
    # WGLMakie uses the same shaders for every experiment, so reusing that
    # verified directory avoids adding another runtime-only asset bundle.
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
    # No page-level heading is drawn in the canvas.  The Streamlit hub already
    # owns that heading, while the extra top and bottom padding protect CJK axis
    # titles and the final explanatory row after browser scaling.
    figure = Figure(
        size = (FIGURE_WIDTH, FIGURE_HEIGHT),
        figure_padding = (18, 18, 22, 32),
    )
    controls = GridLayout()
    metrics = GridLayout()
    figure[2, 1:2] = controls
    figure[3, 1:2] = metrics
    rowsize!(figure.layout, 1, 380)
    rowsize!(figure.layout, 2, 170)
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
    return (; slope, intercept, predicted, residuals, slope_uncertainty)
end

function virtual_source_separation(slit_distance_m, refractive_index, prism_angle_rad)
    return 2.0 * slit_distance_m * (refractive_index - 1.0) * prism_angle_rad
end

function fringe_spacing(wavelength_m, screen_distance_m, source_separation_m)
    source_separation_m > 0 || throw(ArgumentError("虚光源间距必须大于零"))
    return wavelength_m * screen_distance_m / source_separation_m
end

function lens_separation(image_separation_1_m, image_separation_2_m)
    image_separation_1_m > 0 || throw(ArgumentError("第一次像间距必须大于零"))
    image_separation_2_m > 0 || throw(ArgumentError("第二次像间距必须大于零"))
    return sqrt(image_separation_1_m * image_separation_2_m)
end

function wavelength_from_readings(fringe_spacing_m, source_separation_m, screen_distance_m)
    screen_distance_m > 0 || throw(ArgumentError("传播距离必须大于零"))
    return fringe_spacing_m * source_separation_m / screen_distance_m
end

function geometry_model(slit_distance_cm, refractive_index, prism_angle_degree, screen_distance_m)
    slit_distance_m = Float64(slit_distance_cm) / 100.0
    prism_angle_rad = deg2rad(Float64(prism_angle_degree))
    source_separation_m = virtual_source_separation(
        slit_distance_m,
        Float64(refractive_index),
        prism_angle_rad,
    )
    deviation_rad = (Float64(refractive_index) - 1.0) * prism_angle_rad
    beta_d2_m = fringe_spacing(SODIUM_D2_NM * 1.0e-9, Float64(screen_distance_m), source_separation_m)
    beta_d1_m = fringe_spacing(SODIUM_D1_NM * 1.0e-9, Float64(screen_distance_m), source_separation_m)
    beta_reference_m = fringe_spacing(
        SODIUM_REFERENCE_NM * 1.0e-9,
        Float64(screen_distance_m),
        source_separation_m,
    )

    prism_x = slit_distance_m
    # D is measured from the virtual-source/slit plane, not from the prism.
    # This is the same D used by beta=lambda*D/d and lambda=beta*d/D.
    screen_x = Float64(screen_distance_m)
    source_half_mm = 0.5 * source_separation_m * 1000.0
    ray_half_mm = max(2.2, 2.8 * source_half_mm)
    distance_grid = collect(range(0.50, 2.20; length = 120))
    spacing_curve_mm = [
        fringe_spacing(SODIUM_REFERENCE_NM * 1.0e-9, distance, source_separation_m) * 1000.0
        for distance in distance_grid
    ]
    return (;
        slit_distance_m,
        prism_angle_rad,
        deviation_rad,
        source_separation_m,
        beta_d2_m,
        beta_d1_m,
        beta_reference_m,
        prism_x,
        screen_x,
        ray1_x = [0.0, prism_x, screen_x],
        ray1_y = [source_half_mm, 0.55 * source_half_mm, -ray_half_mm],
        ray2_x = [0.0, prism_x, screen_x],
        ray2_y = [-source_half_mm, -0.55 * source_half_mm, ray_half_mm],
        source_points = Point2f[(0.0, source_half_mm), (0.0, -source_half_mm)],
        distance_grid,
        spacing_curve_mm,
        current_spacing_point = Point2f[(Float64(screen_distance_m), beta_reference_m * 1000.0)],
    )
end

function geometry_figure()
    figure, controls, metrics = base_figure()
    optical_axis = Axis(
        figure[1, 1],
        title = "双棱镜形成两相干虚光源",
        xlabel = "沿光轴距离 / m",
        ylabel = "横向位置 / mm",
    )
    spacing_axis = Axis(
        figure[1, 2],
        title = "条纹间距随传播距离变化",
        xlabel = "双棱镜至屏距离 D / m",
        ylabel = "条纹间距 β / mm",
    )

    slit_distance = add_slider!(controls, 1, "狭缝至双棱镜 a", 5:1:25, 10, value -> @sprintf("%.0f cm", value))
    refractive_index = add_slider!(controls, 2, "棱镜折射率 n", 1.45:0.005:1.65, 1.515, value -> @sprintf("%.3f", value))
    prism_angle = add_slider!(controls, 3, "单侧折射角 α", 0.25:0.025:0.80, 0.50, value -> @sprintf("%.3f°", value))
    screen_distance = add_slider!(controls, 4, "虚光源平面至屏 D", 0.50:0.05:1.80, 0.90, value -> @sprintf("%.2f m", value))

    data = lift(
        slit_distance.value,
        refractive_index.value,
        prism_angle.value,
        screen_distance.value,
    ) do a, n, alpha, distance
        geometry_model(Float64(a), Float64(n), Float64(alpha), Float64(distance))
    end

    lines!(optical_axis, lift(value -> value.ray1_x, data), lift(value -> value.ray1_y, data), color = CYAN, linewidth = 2.6, label = "上半棱镜光线")
    lines!(optical_axis, lift(value -> value.ray2_x, data), lift(value -> value.ray2_y, data), color = PINK, linewidth = 2.6, label = "下半棱镜光线")
    scatter!(optical_axis, lift(value -> value.source_points, data), color = AMBER, markersize = 15, label = "虚光源 S₁、S₂")
    vlines!(optical_axis, lift(value -> [value.prism_x], data), color = GREEN, linewidth = 3.0, label = "双棱镜")
    vlines!(optical_axis, lift(value -> [value.screen_x], data), color = (:white, 0.55), linewidth = 2.0, linestyle = :dash, label = "观察屏")
    hlines!(optical_axis, [0.0], color = (:white, 0.20), linestyle = :dot)
    limits!(optical_axis, -0.05, 2.60, -6.0, 6.0)
    axislegend(optical_axis, position = :rb, framevisible = false, labelsize = 11)

    lines!(spacing_axis, lift(value -> value.distance_grid, data), lift(value -> value.spacing_curve_mm, data), color = CYAN, linewidth = 2.8)
    scatter!(spacing_axis, lift(value -> value.current_spacing_point, data), color = AMBER, markersize = 16)
    limits!(spacing_axis, 0.45, 2.25, 0.0, 1.8)

    values = (
        lift(value -> @sprintf("δ = %.3f°", rad2deg(value.deviation_rad)), data),
        lift(value -> @sprintf("d = %.3f mm", value.source_separation_m * 1000.0), data),
        lift(value -> @sprintf("β = %.4f mm", value.beta_reference_m * 1000.0), data),
        Observable(@sprintf("λ参考 = %.1f nm", SODIUM_REFERENCE_NM)),
    )
    detail = Observable("采用小角度近似 d≈2a(n−1)α；钠黄光由 D₂、D₁ 双线组成，教学标称波长为 589.3 nm。")
    add_metrics!(metrics, values, detail)
    return figure
end

function fringes_model(source_separation_mm, screen_distance_m, visibility_percent, span_mm)
    source_separation_m = Float64(source_separation_mm) / 1000.0
    distance_m = Float64(screen_distance_m)
    beta_d2_mm = fringe_spacing(SODIUM_D2_NM * 1.0e-9, distance_m, source_separation_m) * 1000.0
    beta_d1_mm = fringe_spacing(SODIUM_D1_NM * 1.0e-9, distance_m, source_separation_m) * 1000.0
    beta_reference_mm = fringe_spacing(SODIUM_REFERENCE_NM * 1.0e-9, distance_m, source_separation_m) * 1000.0
    visibility = clamp(Float64(visibility_percent) / 100.0, 0.0, 1.0)

    x = collect(range(-Float64(span_mm), Float64(span_mm); length = 1000))
    component_d2 = cos.(2pi .* x ./ beta_d2_mm)
    component_d1 = cos.(2pi .* x ./ beta_d1_mm)
    intensity = 1.0 .+ visibility .* (
        SODIUM_D2_WEIGHT .* component_d2 .+ SODIUM_D1_WEIGHT .* component_d1
    )

    beat_length_mm = abs(beta_d1_mm * beta_d2_mm / (beta_d1_mm - beta_d2_mm))
    beat_fraction = collect(range(-0.5, 0.5; length = 1801))
    beat_x = beat_fraction .* beat_length_mm
    phase_difference = 2pi .* beat_x .* (1.0 / beta_d2_mm - 1.0 / beta_d1_mm)
    envelope = sqrt.(
        SODIUM_D2_WEIGHT^2 .+
        SODIUM_D1_WEIGHT^2 .+
        2.0 * SODIUM_D2_WEIGHT * SODIUM_D1_WEIGHT .* cos.(phase_difference)
    )
    return (;
        source_separation_m,
        distance_m,
        beta_d2_mm,
        beta_d1_mm,
        beta_reference_mm,
        beat_length_mm,
        x,
        intensity,
        beat_x,
        beat_fraction,
        envelope,
    )
end

function fringes_figure()
    figure, controls, metrics = base_figure()
    intensity_axis = Axis(
        figure[1, 1],
        title = "钠黄光干涉条纹",
        xlabel = "屏上位置 x / mm",
        ylabel = "归一化光强",
    )
    envelope_axis = Axis(
        figure[1, 2],
        title = "D 双线引起的可见度包络",
        xlabel = "归一化位置 x/L拍",
        ylabel = "包络可见度",
    )

    separation_values = [DEFAULT_SOURCE_SEPARATION_MM * scale for scale in 0.60:0.05:1.80]
    source_separation = add_slider!(controls, 1, "虚光源间距 d", separation_values, DEFAULT_SOURCE_SEPARATION_MM, value -> @sprintf("%.3f mm", value))
    screen_distance = add_slider!(controls, 2, "虚光源平面至屏 D", 0.50:0.05:1.80, 0.90, value -> @sprintf("%.2f m", value))
    visibility = add_slider!(controls, 3, "基础可见度", 30:5:100, 90, value -> @sprintf("%.0f%%", value))
    span = add_slider!(controls, 4, "近场显示半宽", 2.0:0.5:10.0, 5.0, value -> @sprintf("%.1f mm", value))

    data = lift(
        source_separation.value,
        screen_distance.value,
        visibility.value,
        span.value,
    ) do separation, distance, contrast, half_span
        fringes_model(Float64(separation), Float64(distance), Float64(contrast), Float64(half_span))
    end

    lines!(intensity_axis, lift(value -> value.x, data), lift(value -> value.intensity, data), color = AMBER, linewidth = 2.3)
    hlines!(intensity_axis, [1.0], color = (:white, 0.22), linestyle = :dash)
    limits!(intensity_axis, -10.0, 10.0, -0.05, 2.05)

    lines!(envelope_axis, lift(value -> value.beat_fraction, data), lift(value -> value.envelope, data), color = VIOLET, linewidth = 2.6)
    hlines!(envelope_axis, [1.0], color = (:white, 0.18), linestyle = :dot)
    hlines!(envelope_axis, [abs(SODIUM_D2_WEIGHT - SODIUM_D1_WEIGHT)], color = (PINK, 0.45), linestyle = :dash)
    limits!(envelope_axis, -0.5, 0.5, 0.28, 1.05)

    values = (
        lift(value -> @sprintf("βD₂ = %.4f mm", value.beta_d2_mm), data),
        lift(value -> @sprintf("βD₁ = %.4f mm", value.beta_d1_mm), data),
        lift(value -> @sprintf("β标称 = %.4f mm", value.beta_reference_mm), data),
        lift(value -> @sprintf("拍长 = %.1f mm", value.beat_length_mm), data),
    )
    detail = Observable("钠 D₂、D₁ 线按约 2:1 强度叠加；相消处仍保留 1/3 包络可见度，不会降为零。")
    add_metrics!(metrics, values, detail)
    return figure
end

function separation_model(object_screen_distance_m, focal_length_m, source_separation_mm, reading_uncertainty_um)
    distance_m = Float64(object_screen_distance_m)
    focal_m = Float64(focal_length_m)
    separation_mm = Float64(source_separation_mm)
    reading_uncertainty_mm = Float64(reading_uncertainty_um) / 1000.0
    valid = distance_m > 4.0 * focal_m

    if valid
        conjugate_root = sqrt(distance_m^2 - 4.0 * focal_m * distance_m)
        u_near_m = (distance_m - conjugate_root) / 2.0
        u_far_m = (distance_m + conjugate_root) / 2.0
        v_near_m = distance_m - u_near_m
        v_far_m = distance_m - u_far_m
        magnification_large = v_near_m / u_near_m
        magnification_small = v_far_m / u_far_m
        image_large_mm = separation_mm * magnification_large
        image_small_mm = separation_mm * magnification_small
        recovered_separation_mm = lens_separation(image_large_mm, image_small_mm)
        relative_uncertainty = 0.5 * sqrt(
            (reading_uncertainty_mm / image_large_mm)^2 +
            (reading_uncertainty_mm / image_small_mm)^2,
        )
        separation_uncertainty_mm = recovered_separation_mm * relative_uncertainty
        lens_positions = [u_near_m, u_far_m]
        large_pair = Point2f[(1.0, image_large_mm / 2.0), (1.0, -image_large_mm / 2.0)]
        small_pair = Point2f[(2.0, image_small_mm / 2.0), (2.0, -image_small_mm / 2.0)]
    else
        u_near_m = NaN
        u_far_m = NaN
        v_near_m = NaN
        v_far_m = NaN
        magnification_large = NaN
        magnification_small = NaN
        image_large_mm = NaN
        image_small_mm = NaN
        recovered_separation_mm = NaN
        relative_uncertainty = NaN
        separation_uncertainty_mm = NaN
        lens_positions = Float64[]
        large_pair = Point2f[]
        small_pair = Point2f[]
    end

    return (;
        distance_m,
        focal_m,
        valid,
        u_near_m,
        u_far_m,
        v_near_m,
        v_far_m,
        magnification_large,
        magnification_small,
        image_large_mm,
        image_small_mm,
        separation_mm,
        recovered_separation_mm,
        separation_uncertainty_mm,
        relative_uncertainty,
        reading_uncertainty_mm,
        lens_positions,
        screen_position = [distance_m],
        large_pair,
        small_pair,
    )
end

function separation_figure()
    figure, controls, metrics = base_figure()
    bench_axis = Axis(
        figure[1, 1],
        title = "凸透镜二次成像位置",
        xlabel = "虚光源平面起算位置 / m",
        ylabel = "",
        yticksvisible = false,
        yticklabelsvisible = false,
    )
    image_axis = Axis(
        figure[1, 2],
        title = "两次清晰像的间距",
        xlabel = "共轭透镜位置",
        ylabel = "像的横向位置 / mm",
        xticks = ([1.0, 2.0], ["u₋（大像）", "u₊（小像）"]),
    )

    source_values = [DEFAULT_SOURCE_SEPARATION_MM * scale for scale in 0.60:0.05:1.40]
    object_screen_distance = add_slider!(controls, 1, "物屏距离 D", 0.50:0.05:1.50, 0.90, value -> @sprintf("%.2f m", value))
    focal_length = add_slider!(controls, 2, "凸透镜焦距 f", 0.10:0.01:0.30, 0.20, value -> @sprintf("%.2f m", value))
    source_separation = add_slider!(controls, 3, "虚光源间距 d", source_values, DEFAULT_SOURCE_SEPARATION_MM, value -> @sprintf("%.5f mm", value))
    reading_uncertainty = add_slider!(controls, 4, "像间距读数不确定度", 2:1:30, 10, value -> @sprintf("%.0f μm", value))

    data = lift(
        object_screen_distance.value,
        focal_length.value,
        source_separation.value,
        reading_uncertainty.value,
    ) do distance, focal, separation, uncertainty
        separation_model(
            Float64(distance),
            Float64(focal),
            Float64(separation),
            Float64(uncertainty),
        )
    end

    hlines!(bench_axis, [0.0], color = (:white, 0.34), linewidth = 2.0)
    vlines!(bench_axis, [0.0], color = AMBER, linewidth = 3.0, label = "虚光源平面")
    vlines!(bench_axis, lift(value -> value.screen_position, data), color = (:white, 0.62), linewidth = 3.0, label = "像屏")
    vlines!(bench_axis, lift(value -> value.lens_positions, data), color = CYAN, linewidth = 3.0, label = "两清晰位置 u₋、u₊")
    limits!(bench_axis, -0.04, 1.55, -0.65, 0.65)
    axislegend(bench_axis, position = :rb, framevisible = false, labelsize = 11)

    scatter!(image_axis, lift(value -> value.large_pair, data), color = CYAN, markersize = 19, label = "s大")
    scatter!(image_axis, lift(value -> value.small_pair, data), color = PINK, markersize = 19, label = "s小")
    linesegments!(image_axis, lift(value -> value.large_pair, data), color = CYAN, linewidth = 2.4)
    linesegments!(image_axis, lift(value -> value.small_pair, data), color = PINK, linewidth = 2.4)
    hlines!(image_axis, [0.0], color = (:white, 0.22), linestyle = :dash)
    limits!(image_axis, 0.55, 2.45, -2.2, 2.2)
    axislegend(image_axis, position = :rt, framevisible = false)

    values = (
        lift(value -> value.valid ? @sprintf("u₋/u₊=%.3f/%.3f m", value.u_near_m, value.u_far_m) : "D≤4f：无双位置", data),
        lift(value -> value.valid ? @sprintf("s大=%.4f mm", value.image_large_mm) : "s大=无", data),
        lift(value -> value.valid ? @sprintf("s小=%.4f mm", value.image_small_mm) : "s小=无", data),
        lift(value -> value.valid ? @sprintf("√(s大s小)=%.5f mm", value.recovered_separation_mm) : "d=无法测量", data),
    )
    detail = lift(data) do value
        value.valid ?
            @sprintf(
                "D>4f；u±=(D±√(D²−4fD))/2，放大率 %.3f 与 %.3f 互倒，u(d)=%.1f μm。",
                value.magnification_large,
                value.magnification_small,
                value.separation_uncertainty_mm * 1000.0,
            ) :
            "D≤4f 时薄透镜方程没有两个不同的实数共轭位置，不能用二次成像法测量虚光源间距。"
    end
    add_metrics!(metrics, values, detail)
    return figure
end

function wavelength_model(screen_distance_m, image_separation_1_mm, image_separation_2_mm, half_order, reading_noise_um)
    distance_m = Float64(screen_distance_m)
    d1_mm = Float64(image_separation_1_mm)
    d2_mm = Float64(image_separation_2_mm)
    separation_mm = lens_separation(d1_mm, d2_mm)
    separation_m = separation_mm / 1000.0
    beta_true_mm = fringe_spacing(
        SODIUM_REFERENCE_NM * 1.0e-9,
        distance_m,
        separation_m,
    ) * 1000.0

    order_limit = Int(round(half_order))
    orders = collect(-order_limit:order_limit)
    reading_scale_mm = Float64(reading_noise_um) / 1000.0
    deterministic_error = [
        reading_scale_mm * (0.62 * sin(1.73 * order + 0.4) + 0.38 * cos(0.91 * order - 0.2))
        for order in orders
    ]
    origin_offset_mm = 0.12
    measured_positions_mm = origin_offset_mm .+ beta_true_mm .* orders .+ deterministic_error
    fit = linear_fit(orders, measured_positions_mm)
    fitted_beta_mm = fit.slope
    wavelength_nm = wavelength_from_readings(
        fitted_beta_mm / 1000.0,
        separation_m,
        distance_m,
    ) * 1.0e9

    # Instrument specifications used for propagation are inputs to the
    # uncertainty model, not a preselected final wavelength.
    image_reading_uncertainty_mm = 0.010
    distance_uncertainty_m = 0.001
    relative_d = 0.5 * sqrt(
        (image_reading_uncertainty_mm / d1_mm)^2 +
        (image_reading_uncertainty_mm / d2_mm)^2,
    )
    relative_beta = fit.slope_uncertainty / max(abs(fitted_beta_mm), eps(Float64))
    relative_distance = distance_uncertainty_m / distance_m
    wavelength_uncertainty_nm = abs(wavelength_nm) * sqrt(
        relative_beta^2 + relative_d^2 + relative_distance^2,
    )
    reference_error_percent = 100.0 * (wavelength_nm - SODIUM_REFERENCE_NM) / SODIUM_REFERENCE_NM
    return (;
        distance_m,
        d1_mm,
        d2_mm,
        separation_mm,
        beta_true_mm,
        fitted_beta_mm,
        orders,
        measured_positions_mm,
        predicted_positions_mm = fit.predicted,
        residuals_um = 1000.0 .* fit.residuals,
        slope_uncertainty_mm = fit.slope_uncertainty,
        wavelength_nm,
        wavelength_uncertainty_nm,
        reference_error_percent,
    )
end

function wavelength_figure()
    figure, controls, metrics = base_figure()
    fit_axis = Axis(
        figure[1, 1],
        title = "多级条纹位置线性拟合",
        xlabel = "条纹级次 m",
        ylabel = "显微镜位置 xₘ / mm",
    )
    residual_axis = Axis(
        figure[1, 2],
        title = "拟合残差与读数散布",
        xlabel = "条纹级次 m",
        ylabel = "残差 / μm",
    )

    small_image_values = [DEFAULT_SOURCE_SEPARATION_MM * scale for scale in 0.25:0.025:1.00]
    large_image_values = [DEFAULT_SOURCE_SEPARATION_MM * scale for scale in 1.00:0.05:3.00]
    screen_distance = add_slider!(controls, 1, "虚光源平面至屏 D", 0.50:0.05:1.80, 0.90, value -> @sprintf("%.2f m", value))
    image_1 = add_slider!(controls, 2, "小像间距 s小", small_image_values, DEFAULT_SOURCE_SEPARATION_MM / 2.0, value -> @sprintf("%.4f mm", value))
    image_2 = add_slider!(controls, 3, "大像间距 s大", large_image_values, 2.0 * DEFAULT_SOURCE_SEPARATION_MM, value -> @sprintf("%.4f mm", value))
    half_order = add_slider!(controls, 4, "拟合半级次数 M", 4:1:12, 8, value -> @sprintf("±%.0f 级", value))
    reading_noise = add_slider!(controls, 5, "位置读数散布", 0:1:30, 8, value -> @sprintf("%.0f μm", value))

    data = lift(
        screen_distance.value,
        image_1.value,
        image_2.value,
        half_order.value,
        reading_noise.value,
    ) do distance, d1, d2, order_count, noise
        wavelength_model(
            Float64(distance),
            Float64(d1),
            Float64(d2),
            Int(round(order_count)),
            Float64(noise),
        )
    end

    scatter!(fit_axis, lift(value -> value.orders, data), lift(value -> value.measured_positions_mm, data), color = CYAN, markersize = 12, label = "模拟读数")
    lines!(fit_axis, lift(value -> value.orders, data), lift(value -> value.predicted_positions_mm, data), color = GREEN, linewidth = 2.8, label = "自由截距拟合")
    axislegend(fit_axis, position = :lt, framevisible = false)

    hlines!(residual_axis, [0.0], color = (:white, 0.36), linestyle = :dash)
    scatter!(residual_axis, lift(value -> value.orders, data), lift(value -> value.residuals_um, data), color = AMBER, markersize = 13)

    values = (
        lift(value -> @sprintf("β拟合 = %.5f mm", value.fitted_beta_mm), data),
        lift(value -> @sprintf("d = %.4f mm", value.separation_mm), data),
        lift(value -> @sprintf("λ = %.2f nm", value.wavelength_nm), data),
        lift(value -> @sprintf("u(λ)=%.2f nm", value.wavelength_uncertainty_nm), data),
    )
    detail = lift(data) do value
        @sprintf(
            "由 xₘ=x₀+mβ 拟合 β，再用 λ=βd/D 计算；相对 589.3 nm 的偏差为 %+.3f%%。",
            value.reference_error_percent,
        )
    end
    add_metrics!(metrics, values, detail)
    return figure
end

function run_self_test()
    geometry = geometry_model(10.0, 1.515, 0.50, 0.90)
    expected_d = 2.0 * 0.10 * (1.515 - 1.0) * deg2rad(0.50)
    @assert isapprox(geometry.source_separation_m, expected_d; rtol = 1.0e-12)
    @assert isapprox(geometry.screen_x, 0.90; atol = 1.0e-12)
    @assert isapprox(geometry.source_separation_m * 1000.0, 0.898845; atol = 1.0e-6)
    @assert isapprox(
        geometry.beta_reference_m,
        SODIUM_REFERENCE_NM * 1.0e-9 * 0.90 / expected_d;
        rtol = 1.0e-12,
    )

    fringes = fringes_model(DEFAULT_SOURCE_SEPARATION_MM, 0.90, 90.0, 5.0)
    @assert isapprox(
        fringes.beta_reference_mm,
        SODIUM_REFERENCE_NM * 1.0e-9 * 0.90 / (DEFAULT_SOURCE_SEPARATION_MM / 1000.0) * 1000.0;
        rtol = 1.0e-12,
    )
    @assert fringes.beta_d1_mm > fringes.beta_d2_mm
    @assert minimum(fringes.intensity) >= -1.0e-10
    @assert isapprox(
        minimum(fringes.envelope),
        abs(SODIUM_D2_WEIGHT - SODIUM_D1_WEIGHT);
        atol = 1.0e-10,
    )

    separation = separation_model(0.90, 0.20, DEFAULT_SOURCE_SEPARATION_MM, 10.0)
    @assert separation.valid
    @assert isapprox(separation.u_near_m, 0.30; atol = 1.0e-12)
    @assert isapprox(separation.u_far_m, 0.60; atol = 1.0e-12)
    @assert isapprox(separation.magnification_large, 2.0; atol = 1.0e-12)
    @assert isapprox(separation.magnification_small, 0.5; atol = 1.0e-12)
    @assert isapprox(separation.recovered_separation_mm, DEFAULT_SOURCE_SEPARATION_MM; atol = 1.0e-12)
    @assert separation.separation_uncertainty_mm > 0
    @assert !separation_model(0.70, 0.20, DEFAULT_SOURCE_SEPARATION_MM, 10.0).valid

    small_image_mm = DEFAULT_SOURCE_SEPARATION_MM / 2.0
    large_image_mm = 2.0 * DEFAULT_SOURCE_SEPARATION_MM
    ideal = wavelength_model(0.90, small_image_mm, large_image_mm, 8, 0.0)
    @assert isapprox(ideal.fitted_beta_mm, ideal.beta_true_mm; rtol = 1.0e-12)
    @assert isapprox(ideal.wavelength_nm, SODIUM_REFERENCE_NM; atol = 1.0e-8)
    @assert isapprox(
        wavelength_from_readings(
            ideal.fitted_beta_mm / 1000.0,
            ideal.separation_mm / 1000.0,
            ideal.distance_m,
        ) * 1.0e9,
        ideal.wavelength_nm;
        rtol = 1.0e-12,
    )
    noisy = wavelength_model(0.90, small_image_mm, large_image_mm, 8, 8.0)
    @assert length(noisy.orders) == 17
    @assert isfinite(noisy.wavelength_nm)
    @assert noisy.wavelength_uncertainty_nm > 0
    @assert maximum(abs, noisy.residuals_um) > 0

    for builder in (
        geometry_figure,
        fringes_figure,
        separation_figure,
        wavelength_figure,
    )
        @assert builder() isa Figure
    end
    println("双棱镜干涉四个独立网页实验自检通过：钠黄光模型、二次成像、线性拟合与不确定度均正常。")
end

const PAGE_STYLE = """
html, body { margin: 0; width: 100%; height: 100%; background: #0b0f14; color: #eef3f8; }
body { position: relative; overflow: hidden; font-family: 'Microsoft YaHei', 'Noto Sans CJK SC', sans-serif; }
.biprism-lab { position: absolute; left: 0; top: 0; width: $(FIGURE_WIDTH)px; height: $(FIGURE_HEIGHT)px;
    margin: 0; padding: 0; box-sizing: border-box; overflow: hidden; background: #0b0f14;
    transform-origin: 0 0; }
.biprism-diagnostic {
    position: fixed; left: 16px; right: 16px; bottom: 16px; z-index: 1002;
    display: none; padding: 10px 12px; color: #f7d7d7;
    background: rgba(64, 20, 28, .94); border: 1px solid rgba(255, 85, 105, .65);
    border-radius: 6px; font: 13px/1.5 ui-monospace, Consolas, monospace;
    white-space: pre-wrap;
}
.biprism-diagnostic.visible { display: block; }
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
        const page = document.querySelector(".biprism-lab");
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
        let box = document.getElementById("biprism-diagnostic");
        if (!box) {
            box = document.createElement("div");
            box.id = "biprism-diagnostic";
            box.className = "biprism-diagnostic";
            document.body.appendChild(box);
        }
        box.textContent = detail;
        box.classList.add("visible");
        send("biprism-wgl-failed", detail);
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
            send("biprism-wgl-ready", glStatus);
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
            DOM.div(figure; class = "biprism-lab"),
            DOM.script(CLIENT_STATUS_SCRIPT),
        )
    end
end

function index_app()
    links = [
        DOM.a(name; href = path, style = "color:#73d7cf;margin-right:24px")
        for (name, path) in (
            ("虚光源几何", "./geometry"),
            ("钠黄光干涉条纹", "./fringes"),
            ("二次成像测间距", "./separation"),
            ("波长拟合与不确定度", "./wavelength"),
        )
    ]
    return Bonito.App(
        DOM.div(
            DOM.style(PAGE_STYLE),
            DOM.h1("双棱镜干涉测钠黄光波长"),
            DOM.div(links...),
            style = "padding:32px;background:#0b0f14;color:#eef3f8;min-height:100vh",
        );
        title = "双棱镜干涉测钠黄光波长",
    )
end

function health_app()
    return Bonito.App(
        DOM.pre("physics-experiment:biprism");
        title = "physics-experiment:biprism",
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
    host = get(ENV, "BIPRISM_WEB_HOST", "127.0.0.1")
    port = parse(Int, get(ENV, "BIPRISM_WEB_PORT", "9388"))
    proxy_url = strip(get(ENV, "BIPRISM_WEB_PROXY_URL", "."))
    isempty(proxy_url) && (proxy_url = ".")
    server = Bonito.Server(host, port; proxy_url = proxy_url)
    Bonito.route!(server, "/__physics_health__" => health_app())
    Bonito.route!(server, "/" => index_app())
    Bonito.route!(server, "/geometry" => experiment_app("虚光源几何", geometry_figure))
    Bonito.route!(server, "/fringes" => experiment_app("钠黄光干涉条纹", fringes_figure))
    Bonito.route!(server, "/separation" => experiment_app("二次成像测间距", separation_figure))
    Bonito.route!(server, "/wavelength" => experiment_app("波长拟合与不确定度", wavelength_figure))
    println("双棱镜干涉网页实验已启动：http://$(host):$(port)")
    wait(server)
end

if abspath(PROGRAM_FILE) == @__FILE__
    main()
end
