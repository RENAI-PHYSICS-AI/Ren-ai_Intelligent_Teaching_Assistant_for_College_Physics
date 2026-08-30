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
const Button = WGLMakie.Makie.Button

const TWO_PI = 2pi
const MU0 = 4pi * 1.0e-7
const ELECTRON_ETA = 1.758_820_008_38e11
const SPEED_OF_LIGHT = 299_792_458.0

# Keep the Makie figure, its browser wrapper, and the client-side fit calculation
# on one shared logical size.  The extra vertical space is intentional: Makie
# labels may extend a few pixels beyond their layout cells after CJK font
# shaping, so the final explanatory row needs a real bottom safe area.
const FIGURE_WIDTH = 960
const FIGURE_HEIGHT = 760

const CYAN = RGBf(0.18, 0.78, 0.92)
const PINK = RGBf(0.94, 0.35, 0.50)
const AMBER = RGBf(1.00, 0.72, 0.24)
const GREEN = RGBf(0.36, 0.82, 0.55)
const MUTED = RGBf(0.58, 0.62, 0.70)
const PANEL_BG = RGBf(0.075, 0.085, 0.105)
const BUTTON_BG = RGBf(0.13, 0.15, 0.19)
const CJK_PROBE_TEXT = "电子荷质比可视化实验"
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
        joinpath(Sys.BINDIR, "..", "share", "electron_em", "wglmakie_assets"),
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
            "electron_em",
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
        "未找到真正包含中文字形的字体。请重新执行安装流程，或通过 PHYSICS_CJK_FONT 指定 Noto Sans CJK SC 字体文件。",
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
    figure = Figure(size = (FIGURE_WIDTH, FIGURE_HEIGHT), figure_padding = 18)
    controls = GridLayout()
    metrics = GridLayout()
    figure[2, 1:2] = controls
    figure[3, 1:2] = metrics
    rowsize!(figure.layout, 1, 402)
    rowsize!(figure.layout, 2, 180)
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
        Label(grid[1, column], value, halign = :left)
        colsize!(grid, column, Relative(0.25))
    end
    Label(grid[2, 1:4], detail, color = MUTED, halign = :left)
    rowsize!(grid, 1, 30)
    rowsize!(grid, 2, 48)
    rowgap!(grid, 8)
    return nothing
end

function bind_playback!(grid, row, playback_slider, playback_range, reset_values; step = 1)
    playing = Observable(false)
    playback_values = collect(playback_range)
    numeric_values = Float64.(playback_values)
    generation = Ref(0)
    button_grid = GridLayout()
    grid[1:max(row - 1, 2), 4] = button_grid
    play_button = Button(
        button_grid[1, 1],
        label = "播放",
        height = 31,
        buttoncolor = BUTTON_BG,
        labelcolor = :white,
    )
    reset_button = Button(
        button_grid[2, 1],
        label = "重置",
        height = 31,
        buttoncolor = BUTTON_BG,
        labelcolor = :white,
    )
    rowgap!(button_grid, 8)
    colsize!(grid, 4, Fixed(116))

    on(play_button.clicks) do _
        playing[] = !playing[]
        generation[] += 1
        current_generation = generation[]
        play_button.label[] = playing[] ? "暂停" : "播放"
        if playing[]
            @async begin
                while playing[] && generation[] == current_generation
                    current = Float64(playback_slider.value[])
                    index = argmin(abs.(numeric_values .- current))
                    next_index = mod1(index + step, length(playback_values))
                    set_close_to!(playback_slider, playback_values[next_index])
                    sleep(0.03)
                end
            end
        end
    end
    on(reset_button.clicks) do _
        playing[] = false
        generation[] += 1
        play_button.label[] = "播放"
        for (slider, value) in reset_values
            set_close_to!(slider, value)
        end
    end
    return nothing
end

function helmholtz_axis_field(z, current, radius, turns, separation)
    first_coil = (
        MU0 * turns * current * radius^2 /
        (2 * (radius^2 + (z - separation / 2)^2)^(3 / 2))
    )
    second_coil = (
        MU0 * turns * current * radius^2 /
        (2 * (radius^2 + (z + separation / 2)^2)^(3 / 2))
    )
    return first_coil + second_coil
end

function helmholtz_center_field(current, radius, turns)
    return (4 / 5)^(3 / 2) * MU0 * turns * current / radius
end

function linear_fit(x, y)
    x_mean = sum(x) / length(x)
    y_mean = sum(y) / length(y)
    denominator = sum((value - x_mean)^2 for value in x)
    slope = sum(
        (x[index] - x_mean) * (y[index] - y_mean)
        for index in eachindex(x)
    ) / denominator
    intercept = y_mean - slope * x_mean
    return slope, intercept
end

function circular_model(
    voltage,
    current,
    coil_radius,
    turns,
    residual_microtesla,
    radius_bias_percent,
    progress,
)
    magnetic_field = (
        helmholtz_center_field(current, coil_radius, turns) +
        residual_microtesla * 1.0e-6
    )
    safe_field = abs(magnetic_field) < 1.0e-7 ?
        copysign(1.0e-7, iszero(magnetic_field) ? 1.0 : magnetic_field) :
        magnetic_field
    speed = sqrt(2 * ELECTRON_ETA * voltage)
    radius = speed / (ELECTRON_ETA * abs(safe_field))
    measured_radius = radius * (1 + radius_bias_percent / 100)
    eta_estimate = 2 * voltage / (safe_field^2 * measured_radius^2)
    direction = safe_field > 0 ? -1.0 : 1.0
    theta = collect(range(0.0, direction * TWO_PI; length = 601))
    trajectory = Point2f.(radius .* cos.(theta), radius .* sin.(theta))
    index = clamp(
        floor(Int, progress / 1000 * (length(theta) - 1)) + 1,
        1,
        length(theta),
    )

    fit_voltages = collect(60.0:40.0:300.0)
    fit_radii = [
        sqrt(2 * ELECTRON_ETA * value) /
        (ELECTRON_ETA * abs(safe_field)) *
        (1 + radius_bias_percent / 100)
        for value in fit_voltages
    ]
    fit_x = 1.0e9 .* (abs(safe_field) .* fit_radii) .^ 2
    fit_y = 2 .* fit_voltages
    slope = sum(fit_x .* fit_y) / sum(fit_x .^ 2)
    fit_eta = slope * 1.0e9
    fit_line_x = collect(range(0.0, 3.7; length = 120))
    fit_line_y = slope .* fit_line_x
    current_x = 1.0e9 * (abs(safe_field) * measured_radius)^2
    current_y = 2 * voltage

    return (;
        magnetic_field,
        speed,
        radius,
        measured_radius,
        eta_estimate,
        trajectory,
        trace = trajectory[1:index],
        particle = Point2f[trajectory[index]],
        fit_points = Point2f.(fit_x, fit_y),
        fit_line = Point2f.(fit_line_x, fit_line_y),
        current_fit_point = Point2f[Point2f(current_x, current_y)],
        fit_eta,
    )
end

function circular_figure()
    figure, controls, metrics = base_figure()
    orbit_axis = Axis(
        figure[1, 1],
        title = "电子束轨迹与半径读取",
        xlabel = "x / m",
        ylabel = "y / m",
        aspect = DataAspect(),
    )
    fit_axis = Axis(
        figure[1, 2],
        title = "线性化：2U = η(Br)²",
        xlabel = "(Br)² / 10⁻⁹ T²m²",
        ylabel = "2U / V",
    )

    voltage = add_slider!(controls, 1, "加速电压 U", 50:5:300, 180, value -> @sprintf("%.0f V", value))
    current = add_slider!(controls, 2, "线圈电流 I", -3.0:0.05:3.0, 1.50, value -> @sprintf("%+.2f A", value))
    residual = add_slider!(controls, 3, "剩余磁场 B₀", -100:1:100, 30, value -> @sprintf("%+.0f μT", value))
    radius_bias = add_slider!(controls, 4, "半径读数偏差", -10.0:0.1:10.0, 0.0, value -> @sprintf("%+.1f%%", value))
    progress = add_slider!(controls, 5, "运动进程", 0:1:1000, 250, value -> @sprintf("%.1f%%", value / 10))

    data = lift(
        voltage.value,
        current.value,
        residual.value,
        radius_bias.value,
        progress.value,
    ) do u, i, b0, bias, phase
        circular_model(
            Float64(u),
            Float64(i),
            0.15,
            130,
            Float64(b0),
            Float64(bias),
            Float64(phase),
        )
    end

    lines!(
        orbit_axis,
        lift(value -> value.trajectory, data),
        color = (:white, 0.22),
        linewidth = 1.5,
    )
    lines!(
        orbit_axis,
        lift(value -> value.trace, data),
        color = AMBER,
        linewidth = 3.2,
    )
    scatter!(
        orbit_axis,
        lift(value -> value.particle, data),
        color = PINK,
        markersize = 14,
        strokecolor = :white,
    )
    lines!(
        orbit_axis,
        lift(value -> Point2f[Point2f(0, 0), Point2f(value.measured_radius, 0)], data),
        color = CYAN,
        linewidth = 2.0,
        linestyle = :dash,
    )
    scatter!(
        fit_axis,
        lift(value -> value.fit_points, data),
        color = CYAN,
        markersize = 9,
        label = "多组电压",
    )
    lines!(
        fit_axis,
        lift(value -> value.fit_line, data),
        color = GREEN,
        linewidth = 2.5,
        label = "过原点拟合",
    )
    scatter!(
        fit_axis,
        lift(value -> value.current_fit_point, data),
        color = AMBER,
        markersize = 15,
        label = "当前读数",
    )
    axislegend(fit_axis, position = :lt, framevisible = false)
    limits!(orbit_axis, -0.115, 0.115, -0.115, 0.115)
    limits!(fit_axis, 0.0, 3.7, 0.0, 640.0)

    values = (
        lift(value -> @sprintf("|B| = %.3f mT", 1.0e3abs(value.magnetic_field)), data),
        lift(value -> @sprintf("r读 = %.2f cm", 100value.measured_radius), data),
        lift(value -> @sprintf("η = %.4g C/kg", value.eta_estimate), data),
        lift(value -> @sprintf("拟合误差 = %+.2f%%", 100(value.fit_eta / ELECTRON_ETA - 1)), data),
    )
    detail = lift(data) do value
        if abs(value.magnetic_field) < 5.0e-5
            "总磁场接近零，轨道半径超出观察窗；改变线圈电流可重新获得可测圆轨道。"
        else
            "磁场反向会改变电子弯曲方向；理想磁场不做功，电子速率保持不变。"
        end
    end
    bind_playback!(
        controls,
        6,
        progress,
        0:1:1000,
        [
            (voltage, 180),
            (current, 1.50),
            (residual, 30),
            (radius_bias, 0.0),
            (progress, 250),
        ];
        step = 8,
    )
    add_metrics!(metrics, values, detail)
    return figure
end

function helmholtz_model(
    current,
    radius,
    turns,
    separation_ratio,
    residual_microtesla,
    probe_ratio,
    noise_microtesla,
)
    separation = separation_ratio * radius
    xi = collect(range(-2.0, 2.0; length = 501))
    z = radius .* xi
    fields = [
        helmholtz_axis_field(value, current, radius, turns, separation) +
        residual_microtesla * 1.0e-6
        for value in z
    ]
    probe_field = (
        helmholtz_axis_field(probe_ratio * radius, current, radius, turns, separation) +
        residual_microtesla * 1.0e-6
    )
    center_field = (
        helmholtz_axis_field(0.0, current, radius, turns, separation) +
        residual_microtesla * 1.0e-6
    )
    inner_indices = findall(value -> abs(value) <= 0.25, xi)
    inner_fields = fields[inner_indices]
    uniformity = (
        maximum(inner_fields) - minimum(inner_fields)
    ) / max(abs(center_field), 1.0e-9)

    calibration_current = collect(range(-3.0, 3.0; length = 25))
    true_calibration = [
        helmholtz_axis_field(0.0, value, radius, turns, separation) +
        residual_microtesla * 1.0e-6
        for value in calibration_current
    ]
    measured_calibration = [
        true_calibration[index] +
        noise_microtesla * 1.0e-6 * sin(1.37 * index + 0.4)
        for index in eachindex(calibration_current)
    ]
    measured_millitesla = 1.0e3 .* measured_calibration
    fit_slope, fit_intercept = linear_fit(calibration_current, measured_millitesla)
    fit_current = collect(range(-3.2, 3.2; length = 120))
    fit_field = fit_slope .* fit_current .+ fit_intercept

    return (;
        field_curve = Point2f.(xi, 1.0e3 .* fields),
        probe_point = Point2f[Point2f(probe_ratio, 1.0e3 * probe_field)],
        calibration_points = Point2f.(calibration_current, measured_millitesla),
        calibration_line = Point2f.(fit_current, fit_field),
        current_point = Point2f[Point2f(current, 1.0e3 * center_field)],
        center_field,
        probe_field,
        uniformity,
        fit_slope,
        fit_intercept,
        theoretical_slope = 1.0e3 * helmholtz_axis_field(0.0, 1.0, radius, turns, separation),
    )
end

function helmholtz_figure()
    figure, controls, metrics = base_figure()
    field_axis = Axis(
        figure[1, 1],
        title = "轴向磁场分布",
        xlabel = "归一化位置 z/R",
        ylabel = "B / mT",
    )
    calibration_axis = Axis(
        figure[1, 2],
        title = "霍尔探头 B-I 标定",
        xlabel = "I / A",
        ylabel = "B / mT",
    )

    current = add_slider!(controls, 1, "线圈电流 I", -3.0:0.05:3.0, 1.50, value -> @sprintf("%+.2f A", value))
    radius = add_slider!(controls, 2, "线圈半径 R", 0.10:0.005:0.25, 0.15, value -> @sprintf("%.1f cm", 100value))
    turns = add_slider!(controls, 3, "单线圈匝数 N", 50:5:250, 130, string)
    separation = add_slider!(controls, 4, "间距 s/R", 0.50:0.02:1.50, 1.00, value -> @sprintf("%.2f", value))
    probe = add_slider!(controls, 5, "探头位置 z/R", -2.0:0.02:2.0, 0.0, value -> @sprintf("%+.2f", value))
    noise = add_slider!(controls, 6, "探头读数波动", 0:1:50, 8, value -> @sprintf("%.0f μT", value))

    data = lift(
        current.value,
        radius.value,
        turns.value,
        separation.value,
        probe.value,
        noise.value,
    ) do i, r, n, ratio, z, scatter
        helmholtz_model(
            Float64(i),
            Float64(r),
            Int(n),
            Float64(ratio),
            30.0,
            Float64(z),
            Float64(scatter),
        )
    end

    lines!(
        field_axis,
        lift(value -> value.field_curve, data),
        color = CYAN,
        linewidth = 2.7,
    )
    scatter!(
        field_axis,
        lift(value -> value.probe_point, data),
        color = AMBER,
        markersize = 15,
    )
    vlines!(field_axis, [-0.25, 0.25], color = (:white, 0.22), linestyle = :dash)
    scatter!(
        calibration_axis,
        lift(value -> value.calibration_points, data),
        color = CYAN,
        markersize = 8,
        label = "模拟读数",
    )
    lines!(
        calibration_axis,
        lift(value -> value.calibration_line, data),
        color = GREEN,
        linewidth = 2.5,
        label = "自由截距拟合",
    )
    scatter!(
        calibration_axis,
        lift(value -> value.current_point, data),
        color = AMBER,
        markersize = 14,
        label = "当前电流",
    )
    axislegend(calibration_axis, position = :lt, framevisible = false)
    limits!(field_axis, -2.05, 2.05, -10.0, 10.0)
    limits!(calibration_axis, -3.25, 3.25, -10.0, 10.0)

    values = (
        lift(value -> @sprintf("B(0) = %+.3f mT", 1.0e3value.center_field), data),
        lift(value -> @sprintf("B探头 = %+.3f mT", 1.0e3value.probe_field), data),
        lift(value -> @sprintf("k拟合 = %.3f mT/A", value.fit_slope), data),
        lift(value -> @sprintf("B₀拟合 = %+.1f μT", 1.0e3value.fit_intercept), data),
    )
    detail = lift(data) do value
        @sprintf(
            "|z|≤0.25R 区域峰峰不均匀度 %.3f%%；理论线圈常数 %.3f mT/A。",
            100value.uniformity,
            value.theoretical_slope,
        )
    end
    bind_playback!(
        controls,
        7,
        probe,
        -2.0:0.02:2.0,
        [
            (current, 1.50),
            (radius, 0.15),
            (turns, 130),
            (separation, 1.00),
            (probe, 0.0),
            (noise, 8),
        ];
        step = 2,
    )
    add_metrics!(metrics, values, detail)
    return figure
end

function focus_spot_radius(
    voltage,
    field,
    flight_length,
    divergence_degree,
    spread_percent,
)
    safe_field = max(abs(field), 1.0e-7)
    omega = ELECTRON_ETA * safe_field
    samples = collect(-1.0:0.25:1.0)
    radii = Float64[]
    for sample in samples
        sample_voltage = voltage * max(0.1, 1 + sample * spread_percent / 100)
        speed = sqrt(2 * ELECTRON_ETA * sample_voltage)
        angle = deg2rad(divergence_degree)
        parallel_speed = speed * cos(angle)
        transverse_speed = speed * sin(angle)
        phase = omega * flight_length / parallel_speed
        push!(
            radii,
            abs(2 * transverse_speed / omega * sin(phase / 2)),
        )
    end
    return sqrt(sum(value^2 for value in radii) / length(radii) + (0.0003)^2)
end

function focus_model(voltage, field_millitesla, flight_length, divergence, spread)
    field = field_millitesla * 1.0e-3
    speed = sqrt(2 * ELECTRON_ETA * voltage)
    omega = ELECTRON_ETA * max(abs(field), 1.0e-7)
    normalized_z = collect(range(0.0, 1.0; length = 501))
    z = flight_length .* normalized_z
    factors = (-1.0, -0.55, 0.0, 0.55, 1.0)
    paths = Vector{Vector{Point2f}}()
    for factor in factors
        angle = deg2rad(divergence * factor)
        parallel_speed = speed * cos(angle)
        transverse_speed = speed * sin(angle)
        transverse_position = (
            2 * transverse_speed / omega .*
            sin.(omega .* z ./ (2 * parallel_speed))
        )
        push!(paths, Point2f.(normalized_z, 1.0e3 .* transverse_position))
    end

    field_scan_millitesla = collect(range(0.15, 2.70; length = 420))
    spot_scan_millimetres = [
        1.0e3 * focus_spot_radius(
            voltage,
            value * 1.0e-3,
            flight_length,
            divergence,
            spread,
        )
        for value in field_scan_millitesla
    ]
    turns = omega * flight_length / speed / TWO_PI
    nearest_order = clamp(round(Int, turns), 1, 6)
    current_spot = 1.0e3 * focus_spot_radius(
        voltage,
        field,
        flight_length,
        divergence,
        spread,
    )
    eta_estimate = (
        8pi^2 * nearest_order^2 * voltage /
        (field^2 * flight_length^2)
    )
    focus_fields = [
        order * sqrt(
            8pi^2 * voltage /
            (ELECTRON_ETA * flight_length^2),
        )
        for order in 1:5
    ]
    visible_focus_fields = filter(value -> 0.15e-3 <= value <= 2.70e-3, focus_fields)
    focus_points = [
        Point2f(
            1.0e3 * value,
            1.0e3 * focus_spot_radius(
                voltage,
                value,
                flight_length,
                divergence,
                spread,
            ),
        )
        for value in visible_focus_fields
    ]
    current_point = Point2f[Point2f(field_millitesla, current_spot)]

    return (;
        paths,
        spot_curve = Point2f.(field_scan_millitesla, spot_scan_millimetres),
        focus_points,
        current_point,
        turns,
        nearest_order,
        current_spot,
        eta_estimate,
        speed,
        mismatch = turns - nearest_order,
    )
end

function focus_figure()
    figure, controls, metrics = base_figure()
    beam_axis = Axis(
        figure[1, 1],
        title = "电子束纵向投影",
        xlabel = "归一化飞行距离 z/L",
        ylabel = "横向位移 / mm",
    )
    spot_axis = Axis(
        figure[1, 2],
        title = "荧光屏束斑—磁场曲线",
        xlabel = "B / mT",
        ylabel = "束斑半径 / mm",
    )

    voltage = add_slider!(controls, 1, "加速电压 U", 50:5:300, 180, value -> @sprintf("%.0f V", value))
    magnetic_field = add_slider!(controls, 2, "纵向磁场 B", 0.15:0.005:2.70, 0.815, value -> @sprintf("%.3f mT", value))
    flight_length = add_slider!(controls, 3, "有效长度 L", 0.15:0.005:0.60, 0.35, value -> @sprintf("%.3f m", value))
    divergence = add_slider!(controls, 4, "束流发散半角", 0.2:0.1:5.0, 2.0, value -> @sprintf("%.1f°", value))
    spread = add_slider!(controls, 5, "能量分散", 0.0:0.1:5.0, 1.0, value -> @sprintf("%.1f%%", value))

    data = lift(
        voltage.value,
        magnetic_field.value,
        flight_length.value,
        divergence.value,
        spread.value,
    ) do u, b, length_value, angle, energy_spread
        focus_model(
            Float64(u),
            Float64(b),
            Float64(length_value),
            Float64(angle),
            Float64(energy_spread),
        )
    end

    for path_index in 1:5
        lines!(
            beam_axis,
            lift(value -> value.paths[path_index], data),
            color = path_index == 3 ? AMBER : (CYAN, 0.72),
            linewidth = path_index == 3 ? 2.4 : 1.8,
        )
    end
    vlines!(beam_axis, [1.0], color = PINK, linewidth = 2.0)
    lines!(
        spot_axis,
        lift(value -> value.spot_curve, data),
        color = CYAN,
        linewidth = 2.6,
    )
    scatter!(
        spot_axis,
        lift(value -> value.focus_points, data),
        color = GREEN,
        markersize = 10,
        label = "理论聚焦级次",
    )
    scatter!(
        spot_axis,
        lift(value -> value.current_point, data),
        color = AMBER,
        markersize = 15,
        label = "当前磁场",
    )
    axislegend(spot_axis, position = :rt, framevisible = false)
    limits!(beam_axis, 0.0, 1.02, -60.0, 60.0)
    limits!(spot_axis, 0.1, 2.75, 0.0, 60.0)

    values = (
        lift(value -> @sprintf("回旋周数 = %.3f", value.turns), data),
        lift(value -> "最近级次 n = $(value.nearest_order)", data),
        lift(value -> @sprintf("束斑半径 = %.2f mm", value.current_spot), data),
        lift(value -> @sprintf("η反演误差 = %+.2f%%", 100(value.eta_estimate / ELECTRON_ETA - 1)), data),
    )
    detail = lift(data) do value
        if abs(value.mismatch) < 0.035
            "当前磁场接近第 $(value.nearest_order) 级聚焦；能量分散使理想点聚焦展宽为有限束斑。"
        else
            "继续调节磁场寻找束斑极小值；若聚焦级次判错，η 将按 n² 产生显著偏差。"
        end
    end
    bind_playback!(
        controls,
        6,
        magnetic_field,
        0.15:0.005:2.70,
        [
            (voltage, 180),
            (magnetic_field, 0.815),
            (flight_length, 0.35),
            (divergence, 2.0),
            (spread, 1.0),
        ];
        step = 3,
    )
    add_metrics!(metrics, values, detail)
    return figure
end

function thomson_model(
    voltage,
    electric_kilovolts_per_metre,
    selector_field_millitesla,
    analyser_field_millitesla,
    radius_bias_percent,
)
    electric_field = electric_kilovolts_per_metre * 1.0e3
    selector_field = selector_field_millitesla * 1.0e-3
    analyser_field = analyser_field_millitesla * 1.0e-3
    speed = sqrt(2 * ELECTRON_ETA * voltage)
    selected_speed = electric_field / selector_field
    selector_length = 0.06
    x = collect(range(0.0, selector_length; length = 401))
    transverse_acceleration = -ELECTRON_ETA * (
        electric_field - speed * selector_field
    )
    y = 0.5 .* transverse_acceleration .* (x ./ speed) .^ 2
    exit_offset = last(y)
    slit_half_width = 1.5e-3
    transmitted = abs(exit_offset) <= slit_half_width

    radius = speed / (ELECTRON_ETA * analyser_field)
    measured_radius = radius * (1 + radius_bias_percent / 100)
    theta = collect(range(0.0, 0.78pi; length = 401))
    analysis_x = radius .* sin.(theta)
    analysis_y = -radius .* (1 .- cos.(theta))
    measured_x = measured_radius .* sin.(theta)
    measured_y = -measured_radius .* (1 .- cos.(theta))
    eta_estimate = transmitted ?
        selected_speed / (analyser_field * measured_radius) :
        NaN
    balance = (
        electric_field - speed * selector_field
    ) / max(abs(electric_field), 1.0)

    return (;
        selector_path = Point2f.(100 .* x, 1.0e3 .* y),
        selector_exit = Point2f[Point2f(100selector_length, 1.0e3exit_offset)],
        analysis_path = transmitted ?
            Point2f.(100 .* analysis_x, 100 .* analysis_y) :
            Point2f[],
        measured_path = transmitted ?
            Point2f.(100 .* measured_x, 100 .* measured_y) :
            Point2f[],
        speed,
        selected_speed,
        exit_offset,
        radius,
        measured_radius,
        eta_estimate,
        balance,
        transmitted,
        slit_half_width,
        electric_force_per_charge = electric_field,
        magnetic_force_per_charge = speed * selector_field,
    )
end

function thomson_figure()
    figure, controls, metrics = base_figure()
    selector_axis = Axis(
        figure[1, 1],
        title = "速度选择器：电场力与磁场力竞争",
        xlabel = "选择器位置 x / cm",
        ylabel = "横向偏移 / mm",
    )
    analyser_axis = Axis(
        figure[1, 2],
        title = "分析磁场中的电子圆弧",
        xlabel = "x / cm",
        ylabel = "y / cm",
        aspect = DataAspect(),
    )

    voltage = add_slider!(controls, 1, "加速电压 U", 50:5:400, 180, value -> @sprintf("%.0f V", value))
    electric_field = add_slider!(controls, 2, "选择电场 E", 1.0:0.1:20.0, 8.0, value -> @sprintf("%.1f kV/m", value))
    selector_field = add_slider!(controls, 3, "选择磁场 Bₛ", 0.20:0.01:2.50, 1.00, value -> @sprintf("%.2f mT", value))
    analyser_field = add_slider!(controls, 4, "分析磁场 Bₐ", 0.20:0.01:2.50, 1.00, value -> @sprintf("%.2f mT", value))
    radius_bias = add_slider!(controls, 5, "曲率读数偏差", -10.0:0.1:10.0, 0.0, value -> @sprintf("%+.1f%%", value))

    data = lift(
        voltage.value,
        electric_field.value,
        selector_field.value,
        analyser_field.value,
        radius_bias.value,
    ) do u, e, bs, ba, bias
        thomson_model(
            Float64(u),
            Float64(e),
            Float64(bs),
            Float64(ba),
            Float64(bias),
        )
    end

    hlines!(selector_axis, [0.0], color = (:white, 0.20), linestyle = :dash)
    hlines!(
        selector_axis,
        [-1.5, 1.5],
        color = (PINK, 0.45),
        linestyle = :dot,
    )
    lines!(
        selector_axis,
        lift(value -> value.selector_path, data),
        color = CYAN,
        linewidth = 3.0,
    )
    scatter!(
        selector_axis,
        lift(value -> value.selector_exit, data),
        color = AMBER,
        markersize = 14,
    )
    lines!(
        analyser_axis,
        lift(value -> value.analysis_path, data),
        color = AMBER,
        linewidth = 3.0,
        label = "真实轨迹",
    )
    lines!(
        analyser_axis,
        lift(value -> value.measured_path, data),
        color = CYAN,
        linewidth = 2.0,
        linestyle = :dash,
        label = "读数拟合圆",
    )
    scatter!(analyser_axis, [Point2f(0, 0)], color = PINK, markersize = 11)
    axislegend(analyser_axis, position = :lb, framevisible = false)
    limits!(selector_axis, 0.0, 6.1, -30.0, 30.0)
    limits!(analyser_axis, -4.0, 36.0, -36.0, 4.0)

    values = (
        lift(value -> @sprintf("v真实 = %.3g m/s", value.speed), data),
        lift(value -> @sprintf("E/Bₛ = %.3g m/s", value.selected_speed), data),
        lift(value -> @sprintf("出口偏移 = %+.2f mm", 1.0e3value.exit_offset), data),
        lift(
            value -> value.transmitted ?
                @sprintf("η误差 = %+.2f%%", 100(value.eta_estimate / ELECTRON_ETA - 1)) :
                "η = 不可测",
            data,
        ),
    )
    detail = lift(data) do value
        if value.transmitted
            "电子束通过 ±1.5 mm 选择狭缝：可把 E/Bₛ 作为电子速度用于后续曲率分析。"
        else
            @sprintf(
                "电子束未通过选择狭缝，下游比荷不可测；电、磁力每单位电荷分别为 %.0f 与 %.0f N/C。",
                value.electric_force_per_charge,
                value.magnetic_force_per_charge,
            )
        end
    end
    bind_playback!(
        controls,
        6,
        analyser_field,
        0.20:0.01:2.50,
        [
            (voltage, 180),
            (electric_field, 8.0),
            (selector_field, 1.00),
            (analyser_field, 1.00),
            (radius_bias, 0.0),
        ];
        step = 2,
    )
    add_metrics!(metrics, values, detail)
    return figure
end

function run_self_test()
    expected_center = helmholtz_center_field(1.5, 0.15, 130)
    computed_center = helmholtz_axis_field(0.0, 1.5, 0.15, 130, 0.15)
    @assert isapprox(expected_center, computed_center; rtol = 1.0e-12)
    @assert isapprox(
        helmholtz_axis_field(0.03, 1.5, 0.15, 130, 0.15),
        helmholtz_axis_field(-0.03, 1.5, 0.15, 130, 0.15);
        rtol = 1.0e-12,
    )

    circular = circular_model(180.0, 1.5, 0.15, 130, 0.0, 0.0, 250.0)
    @assert isapprox(circular.eta_estimate, ELECTRON_ETA; rtol = 1.0e-12)
    @assert isapprox(circular.fit_eta, ELECTRON_ETA; rtol = 1.0e-12)

    focus_first = sqrt(
        8pi^2 * 180.0 /
        (ELECTRON_ETA * 0.35^2),
    )
    focus = focus_model(180.0, 1.0e3focus_first, 0.35, 2.0, 0.0)
    @assert isapprox(focus.turns, 1.0; rtol = 1.0e-10)
    @assert focus.nearest_order == 1

    balanced_speed = sqrt(2 * ELECTRON_ETA * 180.0)
    selector_field = 1.0e-3
    balanced_electric = balanced_speed * selector_field
    thomson = thomson_model(
        180.0,
        balanced_electric / 1.0e3,
        1.0,
        1.0,
        0.0,
    )
    @assert abs(thomson.exit_offset) < 1.0e-12
    @assert thomson.transmitted
    @assert isapprox(thomson.eta_estimate, ELECTRON_ETA; rtol = 1.0e-12)
    blocked_thomson = thomson_model(180.0, 1.0, 1.0, 1.0, 0.0)
    @assert !blocked_thomson.transmitted
    @assert isempty(blocked_thomson.analysis_path)
    @assert isnan(blocked_thomson.eta_estimate)

    helmholtz = helmholtz_model(1.5, 0.15, 130, 1.0, 30.0, 0.0, 0.0)
    @assert isapprox(helmholtz.fit_slope, helmholtz.theoretical_slope; rtol = 1.0e-12)
    @assert isapprox(helmholtz.fit_intercept, 0.030; atol = 1.0e-12)

    for builder in (
        circular_figure,
        helmholtz_figure,
        focus_figure,
        thomson_figure,
    )
        @assert builder() isa Figure
    end
    println("电子荷质比四个独立网页实验自检通过。")
end

const PAGE_STYLE = """
html, body { margin: 0; width: 100%; height: 100%; background: #0b0f14; color: #eef3f8; }
body { position: relative; overflow: hidden; font-family: 'Microsoft YaHei', 'Noto Sans CJK SC', sans-serif; }
.electron-em-lab { position: absolute; left: 0; top: 0; width: $(FIGURE_WIDTH)px; height: $(FIGURE_HEIGHT)px;
    margin: 0; padding: 0; box-sizing: border-box; overflow: hidden; background: #0b0f14;
    transform-origin: 0 0; }
.electron-em-diagnostic {
    position: fixed; left: 16px; right: 16px; bottom: 16px; z-index: 1002;
    display: none; padding: 10px 12px; color: #f7d7d7;
    background: rgba(64, 20, 28, .94); border: 1px solid rgba(255, 85, 105, .65);
    border-radius: 6px; font: 13px/1.5 ui-monospace, Consolas, monospace;
    white-space: pre-wrap;
}
.electron-em-diagnostic.visible { display: block; }
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
        const page = document.querySelector(".electron-em-lab");
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
        let box = document.getElementById("electron-em-diagnostic");
        if (!box) {
            box = document.createElement("div");
            box.id = "electron-em-diagnostic";
            box.className = "electron-em-diagnostic";
            document.body.appendChild(box);
        }
        box.textContent = detail;
        box.classList.add("visible");
        send("electron-em-wgl-failed", detail);
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
        if (
            canvas &&
            canvas.width > 0 &&
            canvas.height > 0 &&
            !spinnerVisible
        ) {
            ready = true;
            send("electron-em-wgl-ready", glStatus);
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
            DOM.div(figure; class = "electron-em-lab"),
            DOM.script(CLIENT_STATUS_SCRIPT),
        )
    end
end

function index_app()
    links = [
        DOM.a(name; href = path, style = "color:#73d7cf;margin-right:24px")
        for (name, path) in (
            ("电子束圆轨道法", "./circular"),
            ("亥姆霍兹线圈标定", "./helmholtz"),
            ("纵向磁聚焦法", "./focus"),
            ("汤姆孙交叉场法", "./thomson"),
        )
    ]
    return Bonito.App(
        DOM.div(
            DOM.style(PAGE_STYLE),
            DOM.h1("电子荷质比可视化实验"),
            DOM.div(links...),
            style = "padding:32px;background:#0b0f14;color:#eef3f8;min-height:100vh",
        );
        title = "电子荷质比可视化实验",
    )
end

function health_app()
    return Bonito.App(
        DOM.pre("physics-experiment:electron-em");
        title = "physics-experiment:electron-em",
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
    host = get(ENV, "ELECTRON_EM_WEB_HOST", "127.0.0.1")
    port = parse(Int, get(ENV, "ELECTRON_EM_WEB_PORT", "9386"))
    proxy_url = strip(get(ENV, "ELECTRON_EM_WEB_PROXY_URL", "."))
    isempty(proxy_url) && (proxy_url = ".")
    server = Bonito.Server(host, port; proxy_url = proxy_url)
    Bonito.route!(server, "/__physics_health__" => health_app())
    Bonito.route!(server, "/" => index_app())
    Bonito.route!(server, "/circular" => experiment_app("电子束圆轨道法", circular_figure))
    Bonito.route!(server, "/helmholtz" => experiment_app("亥姆霍兹线圈标定", helmholtz_figure))
    Bonito.route!(server, "/focus" => experiment_app("纵向磁聚焦法", focus_figure))
    Bonito.route!(server, "/thomson" => experiment_app("汤姆孙交叉场法", thomson_figure))
    println("电子荷质比网页实验已启动：http://$(host):$(port)")
    wait(server)
end

if abspath(PROGRAM_FILE) == @__FILE__
    main()
end
