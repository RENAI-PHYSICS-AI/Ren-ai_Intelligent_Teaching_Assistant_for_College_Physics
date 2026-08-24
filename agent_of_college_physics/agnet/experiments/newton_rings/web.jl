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

# The teaching experiment treats the nominal sodium-yellow wavelength as known
# and obtains the plano-convex lens radius from the measured dark-ring diameters.
# It is deliberately fixed rather than exposed as a slider.
const SODIUM_REFERENCE_NM = 589.3
const SODIUM_WAVELENGTH_M = SODIUM_REFERENCE_NM * 1.0e-9
const DEFAULT_RADIUS_M = 1.000
const DEFAULT_FILM_INDEX = 1.000
const DEFAULT_CONTACT_GAP_UM = 0.080
const COURSE_ORDERS = (5, 10, 15, 20, 25, 30)
const COURSE_DIFFERENCE = 15
const RING_GRID_POINTS = 401

const FIGURE_WIDTH = 960
const FIGURE_HEIGHT = 760

const CYAN = RGBf(0.18, 0.78, 0.92)
const PINK = RGBf(0.94, 0.35, 0.50)
const AMBER = RGBf(1.00, 0.72, 0.24)
const GREEN = RGBf(0.36, 0.82, 0.55)
const VIOLET = RGBf(0.61, 0.48, 0.92)
const MUTED = RGBf(0.58, 0.62, 0.70)
const PANEL_BG = RGBf(0.075, 0.085, 0.105)
const CJK_PROBE_TEXT = "牛顿环钠黄光曲率半径逐差测量"
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
    # All experiments use the same WGLMakie shader bundle prepared by the
    # portable runtime.  Reusing it avoids a redundant binary asset directory.
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
    # The outer Streamlit page supplies the experiment heading.  Keeping the
    # canvas to plots, controls and results prevents clipping at both edges.
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

function sample_standard_error(values)
    count = length(values)
    count >= 2 || return 0.0
    mean_value = sum(values) / count
    variance = sum((value - mean_value)^2 for value in values) / (count - 1)
    return sqrt(max(variance, 0.0) / count)
end

function film_thickness(radius_m, curvature_radius_m, contact_gap_m)
    curvature_radius_m > 0 || throw(ArgumentError("曲率半径必须大于零"))
    return contact_gap_m + radius_m^2 / (2.0 * curvature_radius_m)
end

function reflected_intensity(radius_m, curvature_radius_m, wavelength_m, film_index, contact_gap_m)
    wavelength_m > 0 || throw(ArgumentError("波长必须大于零"))
    film_index > 0 || throw(ArgumentError("膜层折射率必须大于零"))
    thickness = film_thickness(radius_m, curvature_radius_m, contact_gap_m)
    # One phase reversal in reflection makes ideal contact dark.
    return sinpi(2.0 * film_index * thickness / wavelength_m)^2
end

function dark_ring_diameter(order, curvature_radius_m, wavelength_m, film_index, contact_gap_m = 0.0)
    radial_square = curvature_radius_m * (
        Float64(order) * wavelength_m / film_index - 2.0 * contact_gap_m
    )
    return radial_square >= 0 ? 2.0 * sqrt(radial_square) : NaN
end

function bright_ring_diameter(order, curvature_radius_m, wavelength_m, film_index, contact_gap_m = 0.0)
    radial_square = curvature_radius_m * (
        (Float64(order) + 0.5) * wavelength_m / film_index - 2.0 * contact_gap_m
    )
    return radial_square >= 0 ? 2.0 * sqrt(radial_square) : NaN
end

function measured_diameters(orders, true_diameters_mm, reading_noise_um; phase = 0.0)
    noise_mm = Float64(reading_noise_um) / 1000.0
    center_mm = 12.0
    left_readings_mm = Float64[]
    right_readings_mm = Float64[]
    measured_mm = Float64[]
    for (index, (order, diameter)) in enumerate(zip(orders, true_diameters_mm))
        left_error = noise_mm * (0.56 * sin(1.19 * order + phase) + 0.24 * cos(0.73 * index))
        right_error = noise_mm * (0.52 * cos(1.07 * order - phase) - 0.21 * sin(0.81 * index))
        left = center_mm - diameter / 2.0 + left_error
        right = center_mm + diameter / 2.0 + right_error
        push!(left_readings_mm, left)
        push!(right_readings_mm, right)
        push!(measured_mm, right - left)
    end
    return (; left_readings_mm, right_readings_mm, measured_mm)
end

function formation_model(curvature_radius_m, film_index, contact_gap_um, radial_span_mm)
    radius_m = Float64(curvature_radius_m)
    index = Float64(film_index)
    gap_m = Float64(contact_gap_um) * 1.0e-6
    span_mm = Float64(radial_span_mm)
    # The outer rings are only about 0.06 mm apart in the default 5 mm
    # field.  A 121×121 grid aliases them into a false tiled/Moiré pattern;
    # 401 samples resolve the narrowest visible fringes without oversampling
    # the independent pages that do not draw the ring image.
    coordinates_mm = collect(range(-span_mm, span_mm; length = RING_GRID_POINTS))
    ring_image = [
        hypot(x_mm, y_mm) <= span_mm ? reflected_intensity(
            hypot(x_mm, y_mm) / 1000.0,
            radius_m,
            SODIUM_WAVELENGTH_M,
            index,
            gap_m,
        ) : 0.0
        for x_mm in coordinates_mm, y_mm in coordinates_mm
    ]
    radial_mm = collect(range(0.0, span_mm; length = 640))
    radial_intensity = [
        reflected_intensity(
            r_mm / 1000.0,
            radius_m,
            SODIUM_WAVELENGTH_M,
            index,
            gap_m,
        )
        for r_mm in radial_mm
    ]
    thickness_um = [
        film_thickness(r_mm / 1000.0, radius_m, gap_m) * 1.0e6
        for r_mm in radial_mm
    ]
    center_intensity = reflected_intensity(
        0.0,
        radius_m,
        SODIUM_WAVELENGTH_M,
        index,
        gap_m,
    )
    maximum_order = floor(Int, 2.0 * index * film_thickness(span_mm / 1000.0, radius_m, gap_m) / SODIUM_WAVELENGTH_M)
    minimum_order = max(0, ceil(Int, 2.0 * index * gap_m / SODIUM_WAVELENGTH_M))
    visible_dark_count = max(0, maximum_order - minimum_order + 1)
    diameter_10_mm = dark_ring_diameter(
        10,
        radius_m,
        SODIUM_WAVELENGTH_M,
        index,
        gap_m,
    ) * 1000.0
    return (;
        radius_m,
        index,
        gap_m,
        span_mm,
        coordinates_mm,
        ring_image,
        radial_mm,
        radial_intensity,
        thickness_um,
        center_intensity,
        minimum_order,
        maximum_order,
        visible_dark_count,
        diameter_10_mm,
    )
end

function formation_figure()
    figure, controls, metrics = base_figure()
    ring_axis = Axis(
        figure[1, 1],
        title = "反射牛顿环（钠黄光 589.3 nm）",
        xlabel = "x / mm",
        ylabel = "y / mm",
        aspect = DataAspect(),
    )
    radial_axis = Axis(
        figure[1, 2],
        title = "径向反射强度",
        xlabel = "半径 r / mm",
        ylabel = "归一化强度",
    )

    curvature_radius = add_slider!(controls, 1, "曲率半径 R", 0.60:0.05:1.40, 1.00, value -> @sprintf("%.2f m", value))
    film_index = add_slider!(controls, 2, "膜层折射率 n", 1.00:0.05:1.50, 1.00, value -> @sprintf("%.2f", value))
    contact_gap = add_slider!(controls, 3, "中心间隙 t₀", 0.00:0.01:0.30, 0.00, value -> @sprintf("%.2f μm", value))
    radial_span = add_slider!(controls, 4, "观察半径", 3.0:0.5:7.0, 5.0, value -> @sprintf("%.1f mm", value))

    data = lift(
        curvature_radius.value,
        film_index.value,
        contact_gap.value,
        radial_span.value,
    ) do radius, index, gap, span
        formation_model(Float64(radius), Float64(index), Float64(gap), Float64(span))
    end

    sodium_colormap = [RGBf(0.01, 0.012, 0.018), RGBf(0.34, 0.22, 0.02), AMBER, RGBf(1.0, 0.95, 0.72)]
    heatmap!(
        ring_axis,
        lift(value -> value.coordinates_mm, data),
        lift(value -> value.coordinates_mm, data),
        lift(value -> value.ring_image, data),
        colormap = sodium_colormap,
        colorrange = (0.0, 1.0),
    )
    lines!(
        radial_axis,
        lift(value -> value.radial_mm, data),
        lift(value -> value.radial_intensity, data),
        color = AMBER,
        linewidth = 2.4,
        label = "反射强度",
    )
    hlines!(radial_axis, [0.0, 1.0], color = (:white, 0.20), linestyle = :dash)
    limits!(radial_axis, 0.0, 7.0, -0.05, 1.05)

    values = (
        lift(value -> @sprintf("I(0) = %.3f", value.center_intensity), data),
        lift(value -> @sprintf("暗环级次 %d…%d", value.minimum_order, value.maximum_order), data),
        lift(value -> @sprintf("可见暗环数 %d", value.visible_dark_count), data),
        lift(value -> isfinite(value.diameter_10_mm) ? @sprintf("D₁₀ = %.4f mm", value.diameter_10_mm) : "D₁₀ 不存在", data),
    )
    detail = lift(data) do value
        @sprintf(
            "t(r)=t₀+r²/(2R)；反射暗环满足 2nt=mλ，亮环满足 2nt=(m+1/2)λ。当前中心膜厚 %.3f μm。",
            value.gap_m * 1.0e6,
        )
    end
    add_metrics!(metrics, values, detail)
    return figure
end

function measurement_model(curvature_radius_m, contact_gap_um, reading_noise_um, selected_order)
    radius_m = Float64(curvature_radius_m)
    gap_m = Float64(contact_gap_um) * 1.0e-6
    orders = collect(COURSE_ORDERS)
    selected = Int(round(selected_order))
    true_diameters_mm = [
        dark_ring_diameter(order, radius_m, SODIUM_WAVELENGTH_M, 1.0, gap_m) * 1000.0
        for order in orders
    ]
    readings = measured_diameters(orders, true_diameters_mm, reading_noise_um; phase = 0.25)
    scan_orders = vcat(reverse(orders), orders)
    scan_positions_mm = vcat(reverse(readings.left_readings_mm), readings.right_readings_mm)
    scan_steps = collect(eachindex(scan_positions_mm))
    selected_index = findfirst(==(selected), orders)
    isnothing(selected_index) && throw(ArgumentError("选中的暗环级次不在课程测量序列中"))
    measured_squared_mm2 = readings.measured_mm .^ 2
    return (;
        radius_m,
        gap_m,
        orders,
        true_diameters_mm,
        left_readings_mm = readings.left_readings_mm,
        right_readings_mm = readings.right_readings_mm,
        measured_diameters_mm = readings.measured_mm,
        measured_squared_mm2,
        scan_orders,
        scan_steps,
        scan_positions_mm,
        scan_is_monotonic = all(diff(scan_positions_mm) .> 0.0),
        selected_order = selected,
        selected_left_mm = readings.left_readings_mm[selected_index],
        selected_right_mm = readings.right_readings_mm[selected_index],
        selected_diameter_mm = readings.measured_mm[selected_index],
    )
end

function measurement_figure()
    figure, controls, metrics = base_figure()
    scan_axis = Axis(
        figure[1, 1],
        title = "读数显微镜全程单向扫描",
        xlabel = "依次读数（左30环 → 中心 → 右30环）",
        ylabel = "显微镜位置 / mm",
        xticks = (collect(1:12), ["左30", "左25", "左20", "左15", "左10", "左5", "右5", "右10", "右15", "右20", "右25", "右30"]),
    )
    diameter_axis = Axis(
        figure[1, 2],
        title = "课程指定暗环直径",
        xlabel = "暗环序数 m",
        ylabel = "Dₘ / mm",
        xticks = (collect(COURSE_ORDERS), collect(string.(COURSE_ORDERS))),
    )

    curvature_radius = add_slider!(controls, 1, "曲率半径 R", 0.60:0.05:1.40, 1.00, value -> @sprintf("%.2f m", value))
    contact_gap = add_slider!(controls, 2, "中心间隙 t₀", 0.00:0.01:0.30, 0.08, value -> @sprintf("%.2f μm", value))
    reading_noise = add_slider!(controls, 3, "读数散布", 0:1:20, 8, value -> @sprintf("%.0f μm", value))
    selected_order = add_slider!(controls, 4, "查看暗环序数", collect(COURSE_ORDERS), 15, value -> @sprintf("m=%.0f", value))

    data = lift(
        curvature_radius.value,
        contact_gap.value,
        reading_noise.value,
        selected_order.value,
    ) do radius, gap, noise, selected
        measurement_model(Float64(radius), Float64(gap), Float64(noise), Int(round(selected)))
    end

    lines!(scan_axis, lift(value -> value.scan_steps, data), lift(value -> value.scan_positions_mm, data), color = GREEN, linewidth = 2.4, label = "单向移动轨迹")
    scatter!(scan_axis, lift(value -> value.scan_steps[1:6], data), lift(value -> value.scan_positions_mm[1:6], data), color = CYAN, markersize = 12, label = "左侧读数")
    scatter!(scan_axis, lift(value -> value.scan_steps[7:12], data), lift(value -> value.scan_positions_mm[7:12], data), color = AMBER, markersize = 12, label = "右侧读数")
    axislegend(scan_axis, position = :lt, framevisible = false, labelsize = 11)
    lines!(diameter_axis, lift(value -> value.orders, data), lift(value -> value.measured_diameters_mm, data), color = VIOLET, linewidth = 2.4)
    scatter!(diameter_axis, lift(value -> value.orders, data), lift(value -> value.measured_diameters_mm, data), color = VIOLET, markersize = 12, label = "D=x右−x左")
    scatter!(diameter_axis, lift(value -> [value.selected_order], data), lift(value -> [value.selected_diameter_mm], data), color = PINK, markersize = 19, label = "当前查看")
    axislegend(diameter_axis, position = :lt, framevisible = false, labelsize = 11)

    values = (
        lift(value -> @sprintf("m=%d 左读数 %.4f mm", value.selected_order, value.selected_left_mm), data),
        lift(value -> @sprintf("右读数 %.4f mm", value.selected_right_mm), data),
        lift(value -> @sprintf("D%d = %.4f mm", value.selected_order, value.selected_diameter_mm), data),
        lift(value -> value.scan_is_monotonic ? "单向序列：通过" : "单向序列：异常", data),
    )
    detail = "按 30、25、20、15、10、5 环左侧，再按 5、10、15、20、25、30 环右侧连续同向读数；不回程，可避免测微鼓轮空程差。"
    add_metrics!(metrics, values, detail)
    return figure
end

function difference_model(curvature_radius_m, contact_gap_um, reading_noise_um, wavelength_uncertainty_nm)
    measurement = measurement_model(curvature_radius_m, contact_gap_um, reading_noise_um, 15)
    lower_orders = [5, 10, 15]
    upper_orders = [20, 25, 30]
    lower_indices = [findfirst(==(order), measurement.orders) for order in lower_orders]
    upper_indices = [findfirst(==(order), measurement.orders) for order in upper_orders]
    delta_squared_mm2 = [
        measurement.measured_squared_mm2[upper] - measurement.measured_squared_mm2[lower]
        for (lower, upper) in zip(lower_indices, upper_indices)
    ]
    radius_estimates_m = [
        delta * 1.0e-6 / (4.0 * SODIUM_WAVELENGTH_M * COURSE_DIFFERENCE)
        for delta in delta_squared_mm2
    ]
    radius_mean_m = sum(radius_estimates_m) / length(radius_estimates_m)
    reading_standard_mm = max(Float64(reading_noise_um), 1.0) / 1000.0 / sqrt(3.0)
    diameter_uncertainty_mm = sqrt(2.0) * reading_standard_mm
    pair_uncertainties_m = Float64[]
    for (lower, upper) in zip(lower_indices, upper_indices)
        d_lower = measurement.measured_diameters_mm[lower]
        d_upper = measurement.measured_diameters_mm[upper]
        delta_uncertainty_mm2 = 2.0 * diameter_uncertainty_mm * sqrt(d_lower^2 + d_upper^2)
        reading_component_m = delta_uncertainty_mm2 * 1.0e-6 / (
            4.0 * SODIUM_WAVELENGTH_M * COURSE_DIFFERENCE
        )
        push!(pair_uncertainties_m, reading_component_m)
    end
    type_a_uncertainty_m = sample_standard_error(radius_estimates_m)
    reading_uncertainty_m = sqrt(sum(value^2 for value in pair_uncertainties_m)) / length(pair_uncertainties_m)
    wavelength_component_m = abs(radius_mean_m) * Float64(wavelength_uncertainty_nm) / SODIUM_REFERENCE_NM
    combined_uncertainty_m = sqrt(type_a_uncertainty_m^2 + reading_uncertainty_m^2 + wavelength_component_m^2)
    return (;
        measurement,
        lower_orders,
        upper_orders,
        pair_labels = ["20−5", "25−10", "30−15"],
        pair_numbers = collect(1:3),
        delta_squared_mm2,
        radius_estimates_m,
        radius_mean_m,
        type_a_uncertainty_m,
        reading_uncertainty_m,
        combined_uncertainty_m,
        relative_error_percent = 100.0 * (radius_mean_m - Float64(curvature_radius_m)) / Float64(curvature_radius_m),
    )
end

function difference_figure()
    figure, controls, metrics = base_figure()
    delta_axis = Axis(
        figure[1, 1],
        title = "m−n=15 的三组直径平方差",
        xlabel = "逐差配对",
        ylabel = "Dₘ²−Dₙ² / mm²",
        xticks = (collect(1:3), ["20−5", "25−10", "30−15"]),
    )
    radius_axis = Axis(
        figure[1, 2],
        title = "每组逐差所得曲率半径",
        xlabel = "逐差配对",
        ylabel = "R / m",
        xticks = (collect(1:3), ["20−5", "25−10", "30−15"]),
    )

    curvature_radius = add_slider!(controls, 1, "真实曲率半径 R", 0.60:0.05:1.40, 1.00, value -> @sprintf("%.2f m", value))
    contact_gap = add_slider!(controls, 2, "中心间隙 t₀", 0.00:0.01:0.30, 0.08, value -> @sprintf("%.2f μm", value))
    reading_noise = add_slider!(controls, 3, "读数散布", 0:1:20, 8, value -> @sprintf("%.0f μm", value))
    wavelength_uncertainty = add_slider!(controls, 4, "钠光波长不确定度", 0.0:0.1:1.0, 0.1, value -> @sprintf("%.1f nm", value))

    data = lift(
        curvature_radius.value,
        contact_gap.value,
        reading_noise.value,
        wavelength_uncertainty.value,
    ) do radius, gap, noise, wavelength_u
        difference_model(Float64(radius), Float64(gap), Float64(noise), Float64(wavelength_u))
    end

    scatter!(delta_axis, lift(value -> value.pair_numbers, data), lift(value -> value.delta_squared_mm2, data), color = CYAN, markersize = 15)
    lines!(delta_axis, lift(value -> value.pair_numbers, data), lift(value -> value.delta_squared_mm2, data), color = CYAN, linewidth = 2.2)
    hlines!(radius_axis, lift(value -> [value.measurement.radius_m], data), color = PINK, linestyle = :dash, linewidth = 2.0, label = "真实 R")
    scatter!(radius_axis, lift(value -> value.pair_numbers, data), lift(value -> value.radius_estimates_m, data), color = AMBER, markersize = 15, label = "逐差 R")
    axislegend(radius_axis, position = :rt, framevisible = false)

    values = (
        lift(value -> @sprintf("R₂₀,₅ = %.4f m", value.radius_estimates_m[1]), data),
        lift(value -> @sprintf("R₂₅,₁₀ = %.4f m", value.radius_estimates_m[2]), data),
        lift(value -> @sprintf("R₃₀,₁₅ = %.4f m", value.radius_estimates_m[3]), data),
        lift(value -> @sprintf("R平均 = %.4f m", value.radius_mean_m), data),
    )
    detail = lift(data) do value
        @sprintf(
            "R=(D²ₘ−D²ₙ)/[4λ(m−n)]，三组均取 m−n=15；中心零差项被消去，u(R)=%.4f m，相对偏差 %+.3f%%。",
            value.combined_uncertainty_m,
            value.relative_error_percent,
        )
    end
    add_metrics!(metrics, values, detail)
    return figure
end

function fit_model(curvature_radius_m, contact_gap_um, reading_noise_um, wavelength_uncertainty_nm)
    measurement = measurement_model(curvature_radius_m, contact_gap_um, reading_noise_um, 15)
    fit = linear_fit(measurement.orders, measurement.measured_squared_mm2)
    radius_fit_m = fit.slope * 1.0e-6 / (4.0 * SODIUM_WAVELENGTH_M)
    slope_component_m = fit.slope_uncertainty * 1.0e-6 / (4.0 * SODIUM_WAVELENGTH_M)
    wavelength_component_m = abs(radius_fit_m) * Float64(wavelength_uncertainty_nm) / SODIUM_REFERENCE_NM
    radius_uncertainty_m = hypot(slope_component_m, wavelength_component_m)
    zero_difference_mm2 = fit.intercept
    inferred_gap_um = -zero_difference_mm2 / (8.0 * radius_fit_m)
    return (;
        measurement,
        predicted_squared_mm2 = fit.predicted,
        residuals_milli_mm2 = fit.residuals .* 1000.0,
        slope_mm2 = fit.slope,
        slope_uncertainty_mm2 = fit.slope_uncertainty,
        zero_difference_mm2,
        inferred_gap_um,
        radius_fit_m,
        radius_uncertainty_m,
        relative_error_percent = 100.0 * (radius_fit_m - Float64(curvature_radius_m)) / Float64(curvature_radius_m),
    )
end

function fit_figure()
    figure, controls, metrics = base_figure()
    fit_axis = Axis(
        figure[1, 1],
        title = "Dₘ²=D₀²+4Rλm 最小二乘拟合",
        xlabel = "暗环序数 m",
        ylabel = "Dₘ² / mm²",
        xticks = (collect(COURSE_ORDERS), collect(string.(COURSE_ORDERS))),
    )
    residual_axis = Axis(
        figure[1, 2],
        title = "六个课程读数的拟合残差",
        xlabel = "暗环序数 m",
        ylabel = "残差 / (10⁻³ mm²)",
        xticks = (collect(COURSE_ORDERS), collect(string.(COURSE_ORDERS))),
    )

    curvature_radius = add_slider!(controls, 1, "真实曲率半径 R", 0.60:0.05:1.40, 1.00, value -> @sprintf("%.2f m", value))
    contact_gap = add_slider!(controls, 2, "中心间隙 t₀", 0.00:0.01:0.30, 0.08, value -> @sprintf("%.2f μm", value))
    reading_noise = add_slider!(controls, 3, "读数散布", 0:1:20, 8, value -> @sprintf("%.0f μm", value))
    wavelength_uncertainty = add_slider!(controls, 4, "钠光波长不确定度", 0.0:0.1:1.0, 0.1, value -> @sprintf("%.1f nm", value))

    data = lift(
        curvature_radius.value,
        contact_gap.value,
        reading_noise.value,
        wavelength_uncertainty.value,
    ) do radius, gap, noise, wavelength_u
        fit_model(Float64(radius), Float64(gap), Float64(noise), Float64(wavelength_u))
    end

    scatter!(fit_axis, lift(value -> value.measurement.orders, data), lift(value -> value.measurement.measured_squared_mm2, data), color = CYAN, markersize = 13, label = "5/10/15/20/25/30 环")
    lines!(fit_axis, lift(value -> value.measurement.orders, data), lift(value -> value.predicted_squared_mm2, data), color = GREEN, linewidth = 2.7, label = "自由截距最小二乘")
    axislegend(fit_axis, position = :lt, framevisible = false)
    hlines!(residual_axis, [0.0], color = (:white, 0.35), linestyle = :dash)
    scatter!(residual_axis, lift(value -> value.measurement.orders, data), lift(value -> value.residuals_milli_mm2, data), color = AMBER, markersize = 13)

    values = (
        lift(value -> @sprintf("A = %.5f mm²/阶", value.slope_mm2), data),
        lift(value -> @sprintf("D₀² = %+.4f mm²", value.zero_difference_mm2), data),
        lift(value -> @sprintf("R拟合 = %.4f m", value.radius_fit_m), data),
        lift(value -> @sprintf("u(R)=%.4f m", value.radius_uncertainty_m), data),
    )
    detail = lift(data) do value
        @sprintf(
            "斜率 A=4Rλ，故 R=A/(4λ)；截距 D₀²不强制为零，并对应中心间隙 %.3f μm。相对偏差 %+.3f%%。",
            value.inferred_gap_um,
            value.relative_error_percent,
        )
    end
    add_metrics!(metrics, values, detail)
    return figure
end

function run_self_test()
    @assert isapprox(
        film_thickness(0.002, 1.0, 0.0),
        2.0e-6;
        rtol = 1.0e-12,
    )
    @assert isapprox(reflected_intensity(0.0, 1.0, SODIUM_WAVELENGTH_M, 1.0, 0.0), 0.0; atol = 1.0e-14)
    first_bright = bright_ring_diameter(0, 1.0, SODIUM_WAVELENGTH_M, 1.0)
    @assert isapprox(first_bright^2, 2.0 * SODIUM_WAVELENGTH_M; rtol = 1.0e-12)

    diameter_10_mm = dark_ring_diameter(10, 1.0, SODIUM_WAVELENGTH_M, 1.0) * 1000.0
    diameter_20_mm = dark_ring_diameter(20, 1.0, SODIUM_WAVELENGTH_M, 1.0) * 1000.0
    @assert isapprox(diameter_10_mm, 4.8551004; atol = 1.0e-7)
    @assert isapprox(diameter_20_mm, 6.8661488; atol = 1.0e-7)
    @assert isapprox(diameter_20_mm^2 - diameter_10_mm^2, 23.572; atol = 1.0e-9)

    measurement = measurement_model(1.0, 0.20, 0.0, 15)
    @assert measurement.orders == collect(COURSE_ORDERS)
    @assert measurement.scan_orders == [30, 25, 20, 15, 10, 5, 5, 10, 15, 20, 25, 30]
    @assert measurement.scan_is_monotonic
    @assert isapprox(measurement.selected_diameter_mm, dark_ring_diameter(15, 1.0, SODIUM_WAVELENGTH_M, 1.0, 0.20e-6) * 1000.0; atol = 1.0e-10)

    difference = difference_model(1.0, 0.20, 0.0, 0.1)
    @assert difference.lower_orders == [5, 10, 15]
    @assert difference.upper_orders == [20, 25, 30]
    @assert all(isapprox(value, 1.0; atol = 1.0e-10) for value in difference.radius_estimates_m)
    @assert isapprox(difference.radius_mean_m, 1.0; atol = 1.0e-10)
    @assert difference.combined_uncertainty_m > 0

    fit = fit_model(1.0, 0.20, 0.0, 0.1)
    @assert isapprox(fit.slope_mm2, 2.3572; atol = 1.0e-10)
    @assert isapprox(fit.zero_difference_mm2, -1.600; atol = 1.0e-10)
    @assert isapprox(fit.radius_fit_m, 1.0; atol = 1.0e-10)
    @assert isapprox(fit.inferred_gap_um, 0.20; atol = 1.0e-10)
    @assert fit.radius_uncertainty_m > 0
    noisy_fit = fit_model(1.0, 0.08, 8.0, 0.1)
    @assert isfinite(noisy_fit.radius_fit_m)
    @assert noisy_fit.slope_uncertainty_mm2 > 0

    @assert isnan(dark_ring_diameter(0, 1.0, SODIUM_WAVELENGTH_M, 1.0, 0.20e-6))
    formation = formation_model(1.0, 1.0, 0.00, 5.0)
    @assert size(formation.ring_image) == (RING_GRID_POINTS, RING_GRID_POINTS)
    @assert formation.ring_image == reverse(formation.ring_image; dims = (1, 2))
    @assert formation.center_intensity == 0.0
    @assert formation.ring_image[1, 1] == 0.0
    for builder in (
        formation_figure,
        measurement_figure,
        difference_figure,
        fit_figure,
    )
        @assert builder() isa Figure
    end
    println("牛顿环四个独立网页实验自检通过：等厚干涉、单向显微镜读数、15级逐差与最小二乘拟合均正常。")
end

const PAGE_STYLE = """
html, body { margin: 0; width: 100%; height: 100%; background: #0b0f14; color: #eef3f8; }
body { position: relative; overflow: hidden; font-family: 'Microsoft YaHei', 'Noto Sans CJK SC', sans-serif; }
.newton-rings-lab { position: absolute; left: 0; top: 0; width: $(FIGURE_WIDTH)px; height: $(FIGURE_HEIGHT)px;
    margin: 0; padding: 0; box-sizing: border-box; overflow: hidden; background: #0b0f14;
    transform-origin: 0 0; }
.newton-rings-diagnostic {
    position: fixed; left: 16px; right: 16px; bottom: 16px; z-index: 1002;
    display: none; padding: 10px 12px; color: #f7d7d7;
    background: rgba(64, 20, 28, .94); border: 1px solid rgba(255, 85, 105, .65);
    border-radius: 6px; font: 13px/1.5 ui-monospace, Consolas, monospace;
    white-space: pre-wrap;
}
.newton-rings-diagnostic.visible { display: block; }
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
        const page = document.querySelector(".newton-rings-lab");
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
        let box = document.getElementById("newton-rings-diagnostic");
        if (!box) {
            box = document.createElement("div");
            box.id = "newton-rings-diagnostic";
            box.className = "newton-rings-diagnostic";
            document.body.appendChild(box);
        }
        box.textContent = detail;
        box.classList.add("visible");
        send("newton-rings-wgl-failed", detail);
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
            send("newton-rings-wgl-ready", glStatus);
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
            DOM.div(figure; class = "newton-rings-lab"),
            DOM.script(CLIENT_STATUS_SCRIPT),
        )
    end
end

function index_app()
    links = [
        DOM.a(name; href = path, style = "color:#73d7cf;margin-right:24px")
        for (name, path) in (
            ("干涉形成", "./formation"),
            ("读数显微镜单向测量", "./measurement"),
            ("15级逐差法", "./difference"),
            ("最小二乘拟合", "./fit"),
        )
    ]
    return Bonito.App(
        DOM.div(
            DOM.style(PAGE_STYLE),
            DOM.h1("牛顿环测量曲率半径（钠黄光）"),
            DOM.div(links...),
            style = "padding:32px;background:#0b0f14;color:#eef3f8;min-height:100vh",
        );
        title = "牛顿环测量曲率半径（钠黄光）",
    )
end

function health_app()
    return Bonito.App(
        DOM.pre("physics-experiment:newton-rings");
        title = "physics-experiment:newton-rings",
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
    host = get(ENV, "NEWTON_RINGS_WEB_HOST", "127.0.0.1")
    port = parse(Int, get(ENV, "NEWTON_RINGS_WEB_PORT", "9389"))
    proxy_url = strip(get(ENV, "NEWTON_RINGS_WEB_PROXY_URL", "."))
    isempty(proxy_url) && (proxy_url = ".")
    server = Bonito.Server(host, port; proxy_url = proxy_url)
    Bonito.route!(server, "/__physics_health__" => health_app())
    Bonito.route!(server, "/" => index_app())
    Bonito.route!(server, "/formation" => experiment_app("牛顿环形成", formation_figure))
    Bonito.route!(server, "/measurement" => experiment_app("读数显微镜单向测量", measurement_figure))
    Bonito.route!(server, "/difference" => experiment_app("15级逐差法求曲率半径", difference_figure))
    Bonito.route!(server, "/fit" => experiment_app("直径平方最小二乘拟合", fit_figure))
    println("牛顿环网页实验已启动：http://$(host):$(port)")
    wait(server)
end

if abspath(PROGRAM_FILE) == @__FILE__
    main()
end
