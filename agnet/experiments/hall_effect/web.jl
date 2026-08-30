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

const MU0 = 4pi * 1.0e-7
const FIGURE_WIDTH = 960
const FIGURE_HEIGHT = 760
const HEALTH_MARKER = "physics-experiment:hall-effect"
const CALIBRATION_COIL_CONSTANT = 20.0 # mT/A
const DEFAULT_SENSITIVITY = 2.50       # mV/mT at 10 mA control current

const CYAN = RGBf(0.18, 0.78, 0.92)
const PINK = RGBf(0.94, 0.35, 0.50)
const AMBER = RGBf(1.00, 0.72, 0.24)
const GREEN = RGBf(0.36, 0.82, 0.55)
const MUTED = RGBf(0.58, 0.62, 0.70)
const PANEL_BG = RGBf(0.075, 0.085, 0.105)
const BUTTON_BG = RGBf(0.13, 0.15, 0.19)
const CJK_PROBE_TEXT = "霍尔效应测磁场分布可视化实验"
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
    asset_dir = normpath(joinpath(Sys.BINDIR, "..", "share", "hall_effect", "wglmakie_assets"))
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
    julia_font = normpath(joinpath(Sys.BINDIR, "..", "share", "hall_effect", "fonts", "NotoSansCJKsc-Regular.otf"))
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
    rowsize!(figure.layout, 1, 390)
    rowsize!(figure.layout, 2, 205)
    rowsize!(figure.layout, 3, 105)
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
    rowsize!(grid, 2, 46)
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
                    sleep(0.035)
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

function linear_fit(x, y)
    length(x) == length(y) || throw(ArgumentError("拟合数据长度不一致"))
    length(x) >= 2 || throw(ArgumentError("线性拟合至少需要两个点"))
    x_mean = sum(x) / length(x)
    y_mean = sum(y) / length(y)
    denominator = sum((value - x_mean)^2 for value in x)
    denominator > 0 || throw(ArgumentError("自变量不能全部相同"))
    slope = sum((x[i] - x_mean) * (y[i] - y_mean) for i in eachindex(x)) / denominator
    intercept = y_mean - slope * x_mean
    residuals = y .- (slope .* x .+ intercept)
    residual_sd = length(x) > 2 ? sqrt(sum(residuals .^ 2) / (length(x) - 2)) : 0.0
    slope_se = residual_sd / sqrt(denominator)
    return (; slope, intercept, residuals, residual_sd, slope_se)
end

function sample_standard_deviation(values)
    length(values) <= 1 && return 0.0
    mean_value = sum(values) / length(values)
    return sqrt(sum((value - mean_value)^2 for value in values) / (length(values) - 1))
end

deterministic_noise(index, amplitude) = amplitude * (0.62sin(1.37index + 0.31) + 0.38cos(0.73index - 0.22))

function calibration_model(
    coil_current,
    sensor_current_ma,
    nominal_sensitivity,
    offset_mv,
    noise_uv,
    progress,
)
    full_currents = collect(range(-2.0, 2.0; length = 21))
    full_fields = CALIBRATION_COIL_CONSTANT .* full_currents
    effective_sensitivity = nominal_sensitivity * sensor_current_ma / 10.0
    full_voltages = [
        effective_sensitivity * field + offset_mv + deterministic_noise(i, noise_uv / 1000.0)
        for (i, field) in enumerate(full_fields)
    ]
    visible_count = clamp(floor(Int, progress / 1000 * 18) + 3, 3, length(full_fields))
    fields = full_fields[1:visible_count]
    voltages = full_voltages[1:visible_count]
    fit = linear_fit(fields, voltages)
    line_fields = collect(range(-42.0, 42.0; length = 160))
    current_field = CALIBRATION_COIL_CONSTANT * coil_current
    current_voltage = effective_sensitivity * current_field + offset_mv
    estimated_field = (current_voltage - fit.intercept) / fit.slope
    max_residual = maximum(abs.(fit.residuals))
    return (;
        points = Point2f.(fields, voltages),
        fit_line = Point2f.(line_fields, fit.slope .* line_fields .+ fit.intercept),
        residual_points = Point2f.(fields, 1000.0 .* fit.residuals),
        current_point = Point2f[Point2f(current_field, current_voltage)],
        current_field,
        current_voltage,
        estimated_field,
        fitted_sensitivity = fit.slope,
        fitted_offset = fit.intercept,
        max_residual_uv = 1000.0 * max_residual,
        visible_count,
    )
end

function calibration_figure()
    figure, controls, metrics = base_figure()
    calibration_axis = Axis(
        figure[1, 1],
        title = "霍尔电压—磁感应强度标定",
        xlabel = "B / mT",
        ylabel = "U_H / mV",
    )
    residual_axis = Axis(
        figure[1, 2],
        title = "标定残差",
        xlabel = "B / mT",
        ylabel = "残差 / μV",
    )

    coil_current = add_slider!(controls, 1, "励磁电流 I", -2.0:0.02:2.0, 1.20, value -> @sprintf("%+.2f A", value))
    sensor_current = add_slider!(controls, 2, "霍尔控制电流 I_H", 4.0:0.2:16.0, 10.0, value -> @sprintf("%.1f mA", value))
    sensitivity = add_slider!(controls, 3, "额定灵敏度 S", 1.5:0.02:3.5, DEFAULT_SENSITIVITY, value -> @sprintf("%.2f mV/mT", value))
    offset = add_slider!(controls, 4, "零场偏置 U₀", -8.0:0.1:8.0, 1.2, value -> @sprintf("%+.1f mV", value))
    noise = add_slider!(controls, 5, "电压读数噪声", 0:2:100, 20, value -> @sprintf("%.0f μV", value))
    progress = add_slider!(controls, 6, "采集进程", 0:1:1000, 1000, value -> @sprintf("%.1f%%", value / 10))

    data = lift(
        coil_current.value,
        sensor_current.value,
        sensitivity.value,
        offset.value,
        noise.value,
        progress.value,
    ) do coil, sensor, gain, zero, scatter, phase
        calibration_model(Float64(coil), Float64(sensor), Float64(gain), Float64(zero), Float64(scatter), Float64(phase))
    end

    scatter!(calibration_axis, lift(value -> value.points, data), color = CYAN, markersize = 9, label = "标定读数")
    lines!(calibration_axis, lift(value -> value.fit_line, data), color = GREEN, linewidth = 2.5, label = "线性拟合")
    scatter!(calibration_axis, lift(value -> value.current_point, data), color = AMBER, markersize = 15, label = "当前工作点")
    axislegend(calibration_axis, position = :lt, framevisible = false)
    scatter!(residual_axis, lift(value -> value.residual_points, data), color = PINK, markersize = 9)
    hlines!(residual_axis, [0.0], color = (:white, 0.25), linestyle = :dash)
    limits!(calibration_axis, -43.0, 43.0, -130.0, 130.0)
    limits!(residual_axis, -43.0, 43.0, -120.0, 120.0)

    values = (
        lift(value -> @sprintf("S拟合 = %.4f mV/mT", value.fitted_sensitivity), data),
        lift(value -> @sprintf("U₀拟合 = %+.3f mV", value.fitted_offset), data),
        lift(value -> @sprintf("B读数 = %+.3f mT", value.estimated_field), data),
        lift(value -> @sprintf("最大残差 = %.1f μV", value.max_residual_uv), data),
    )
    detail = lift(data) do value
        @sprintf("已采集 %d/21 个点；正负磁场标定可分离零场偏置，控制电流改变时必须重新标定灵敏度。", value.visible_count)
    end
    bind_playback!(
        controls,
        7,
        progress,
        0:1:1000,
        [
            (coil_current, 1.20),
            (sensor_current, 10.0),
            (sensitivity, DEFAULT_SENSITIVITY),
            (offset, 1.2),
            (noise, 20),
            (progress, 1000),
        ];
        step = 8,
    )
    add_metrics!(metrics, values, detail)
    return figure
end

function finite_solenoid_field(z, current, turns, length_m, radius_m)
    half_length = length_m / 2
    left = (z + half_length) / sqrt(radius_m^2 + (z + half_length)^2)
    right = (z - half_length) / sqrt(radius_m^2 + (z - half_length)^2)
    return MU0 * turns * current / (2length_m) * (left - right)
end

function scan_model(
    current,
    turns,
    length_m,
    radius_m,
    sensitivity,
    offset_mv,
    position_m,
    noise_uv,
)
    positions = collect(range(-0.30, 0.30; length = 241))
    true_fields_mt = 1000.0 .* [
        finite_solenoid_field(z, current, turns, length_m, radius_m)
        for z in positions
    ]
    hall_voltages_mv = [
        sensitivity * field + offset_mv + deterministic_noise(i, noise_uv / 1000.0)
        for (i, field) in enumerate(true_fields_mt)
    ]
    measured_fields_mt = (hall_voltages_mv .- offset_mv) ./ sensitivity
    probe_index = argmin(abs.(positions .- position_m))
    left_index = max(probe_index - 1, 1)
    right_index = min(probe_index + 1, length(positions))
    center_indices = findall(z -> abs(z) <= 0.05, positions)
    center_fields = true_fields_mt[center_indices]
    center_field = finite_solenoid_field(0.0, current, turns, length_m, radius_m) * 1000.0
    uniformity = (maximum(center_fields) - minimum(center_fields)) / max(abs(center_field), 1.0e-12)
    return (;
        true_curve = Point2f.(100.0 .* positions, true_fields_mt),
        measured_curve = Point2f.(100.0 .* positions, measured_fields_mt),
        voltage_curve = Point2f.(100.0 .* positions, hall_voltages_mv),
        probe_field_point = Point2f[Point2f(100position_m, measured_fields_mt[probe_index])],
        probe_voltage_point = Point2f[Point2f(100position_m, hall_voltages_mv[probe_index])],
        probe_field = measured_fields_mt[probe_index],
        probe_voltage = hall_voltages_mv[probe_index],
        center_field,
        uniformity,
        gradient = probe_index in (1, length(positions)) ? 0.0 :
            (measured_fields_mt[right_index] - measured_fields_mt[left_index]) /
            (100positions[right_index] - 100positions[left_index]),
    )
end

function scan_figure()
    figure, controls, metrics = base_figure()
    field_axis = Axis(
        figure[1, 1],
        title = "螺线管轴向磁场分布",
        xlabel = "轴向位置 z / cm",
        ylabel = "B / mT",
    )
    voltage_axis = Axis(
        figure[1, 2],
        title = "霍尔探头扫描电压",
        xlabel = "轴向位置 z / cm",
        ylabel = "U_H / mV",
    )

    current = add_slider!(controls, 1, "励磁电流 I", -2.0:0.02:2.0, 1.20, value -> @sprintf("%+.2f A", value))
    turns = add_slider!(controls, 2, "线圈总匝数 N", 400:20:1600, 1000, string)
    length_m = add_slider!(controls, 3, "螺线管长度 L", 0.20:0.01:0.50, 0.36, value -> @sprintf("%.0f cm", 100value))
    radius_m = add_slider!(controls, 4, "螺线管半径 R", 0.03:0.002:0.09, 0.06, value -> @sprintf("%.1f cm", 100value))
    sensitivity = add_slider!(controls, 5, "探头灵敏度 S", 1.5:0.02:3.5, DEFAULT_SENSITIVITY, value -> @sprintf("%.2f mV/mT", value))
    position = add_slider!(controls, 6, "探头位置 z", -0.30:0.003:0.30, 0.0, value -> @sprintf("%+.1f cm", 100value))
    noise = add_slider!(controls, 7, "电压读数噪声", 0:2:100, 20, value -> @sprintf("%.0f μV", value))

    data = lift(
        current.value,
        turns.value,
        length_m.value,
        radius_m.value,
        sensitivity.value,
        position.value,
        noise.value,
    ) do i, n, length_value, radius_value, gain, z, scatter
        scan_model(
            Float64(i),
            Int(n),
            Float64(length_value),
            Float64(radius_value),
            Float64(gain),
            1.2,
            Float64(z),
            Float64(scatter),
        )
    end

    lines!(field_axis, lift(value -> value.true_curve, data), color = CYAN, linewidth = 2.7, label = "有限长线圈理论")
    lines!(field_axis, lift(value -> value.measured_curve, data), color = GREEN, linewidth = 2.0, linestyle = :dash, label = "霍尔探头反演")
    scatter!(field_axis, lift(value -> value.probe_field_point, data), color = AMBER, markersize = 15, label = "当前位置")
    vlines!(field_axis, [-5.0, 5.0], color = (:white, 0.22), linestyle = :dash)
    axislegend(field_axis, position = :lt, framevisible = false)
    lines!(voltage_axis, lift(value -> value.voltage_curve, data), color = PINK, linewidth = 2.6)
    scatter!(voltage_axis, lift(value -> value.probe_voltage_point, data), color = AMBER, markersize = 15)
    limits!(field_axis, -30.5, 30.5, -8.0, 8.0)
    limits!(voltage_axis, -30.5, 30.5, -20.0, 20.0)

    values = (
        lift(value -> @sprintf("B(0) = %+.3f mT", value.center_field), data),
        lift(value -> @sprintf("B(z) = %+.3f mT", value.probe_field), data),
        lift(value -> @sprintf("U_H = %+.3f mV", value.probe_voltage), data),
        lift(value -> @sprintf("dB/dz = %+.3f mT/cm", value.gradient), data),
    )
    detail = lift(data) do value
        @sprintf("中心 ±5 cm 区域峰峰不均匀度 %.3f%%；探头敏感面应垂直于待测磁场，位置零点应单独校准。", 100value.uniformity)
    end
    bind_playback!(
        controls,
        8,
        position,
        -0.30:0.003:0.30,
        [
            (current, 1.20),
            (turns, 1000),
            (length_m, 0.36),
            (radius_m, 0.06),
            (sensitivity, DEFAULT_SENSITIVITY),
            (position, 0.0),
            (noise, 20),
        ];
        step = 2,
    )
    add_metrics!(metrics, values, detail)
    return figure
end

function fit_model(point_count, sensitivity, offset_mv, nonlinearity_percent, noise_uv, progress)
    full_fields = collect(range(-80.0, 80.0; length = point_count))
    full_voltages = [
        sensitivity * field * (1 + nonlinearity_percent / 100 * (field / 80.0)^2) +
        offset_mv + deterministic_noise(i, noise_uv / 1000.0)
        for (i, field) in enumerate(full_fields)
    ]
    visible_count = clamp(floor(Int, progress / 1000 * (point_count - 3)) + 3, 3, point_count)
    fields = full_fields[1:visible_count]
    voltages = full_voltages[1:visible_count]
    fit = linear_fit(fields, voltages)
    line_fields = collect(range(-84.0, 84.0; length = 180))
    fitted = fit.slope .* fields .+ fit.intercept
    ss_res = sum((voltages .- fitted) .^ 2)
    y_mean = sum(voltages) / length(voltages)
    ss_tot = sum((voltages .- y_mean) .^ 2)
    r_squared = ss_tot > 0 ? 1 - ss_res / ss_tot : 1.0
    sensitivity_error = 100 * (fit.slope / sensitivity - 1)
    return (;
        points = Point2f.(fields, voltages),
        fit_line = Point2f.(line_fields, fit.slope .* line_fields .+ fit.intercept),
        residual_points = Point2f.(fields, 1000.0 .* fit.residuals),
        slope = fit.slope,
        intercept = fit.intercept,
        slope_se = fit.slope_se,
        residual_sd_uv = 1000.0 * fit.residual_sd,
        r_squared,
        sensitivity_error,
        visible_count,
        point_count,
    )
end

function fit_figure()
    figure, controls, metrics = base_figure()
    fit_axis = Axis(
        figure[1, 1],
        title = "多点标定与自由截距拟合",
        xlabel = "参考磁场 B_ref / mT",
        ylabel = "霍尔电压 U_H / mV",
    )
    residual_axis = Axis(
        figure[1, 2],
        title = "残差诊断非线性",
        xlabel = "参考磁场 B_ref / mT",
        ylabel = "U_H - U_fit / μV",
    )

    point_count = add_slider!(controls, 1, "标定点数 n", 7:2:31, 21, string)
    sensitivity = add_slider!(controls, 2, "真实灵敏度 S", 1.5:0.02:3.5, DEFAULT_SENSITIVITY, value -> @sprintf("%.2f mV/mT", value))
    offset = add_slider!(controls, 3, "零场偏置 U₀", -8.0:0.1:8.0, 1.2, value -> @sprintf("%+.1f mV", value))
    nonlinearity = add_slider!(controls, 4, "满量程非线性", -2.0:0.05:2.0, 0.30, value -> @sprintf("%+.2f%%", value))
    noise = add_slider!(controls, 5, "电压读数噪声", 0:2:100, 20, value -> @sprintf("%.0f μV", value))
    progress = add_slider!(controls, 6, "拟合采集进程", 0:1:1000, 1000, value -> @sprintf("%.1f%%", value / 10))

    data = lift(
        point_count.value,
        sensitivity.value,
        offset.value,
        nonlinearity.value,
        noise.value,
        progress.value,
    ) do n, gain, zero, curvature, scatter, phase
        fit_model(Int(n), Float64(gain), Float64(zero), Float64(curvature), Float64(scatter), Float64(phase))
    end

    scatter!(fit_axis, lift(value -> value.points, data), color = CYAN, markersize = 9, label = "模拟测量")
    lines!(fit_axis, lift(value -> value.fit_line, data), color = GREEN, linewidth = 2.5, label = "最小二乘拟合")
    axislegend(fit_axis, position = :lt, framevisible = false)
    scatter!(residual_axis, lift(value -> value.residual_points, data), color = PINK, markersize = 9)
    hlines!(residual_axis, [0.0], color = (:white, 0.25), linestyle = :dash)
    limits!(fit_axis, -85.0, 85.0, -310.0, 310.0)
    limits!(residual_axis, -85.0, 85.0, -2500.0, 2500.0)

    values = (
        lift(value -> @sprintf("S = %.5f ± %.5f mV/mT", value.slope, value.slope_se), data),
        lift(value -> @sprintf("U₀ = %+.4f mV", value.intercept), data),
        lift(value -> @sprintf("R² = %.7f", value.r_squared), data),
        lift(value -> @sprintf("s残差 = %.1f μV", value.residual_sd_uv), data),
    )
    detail = lift(data) do value
        @sprintf(
            "已纳入 %d/%d 点；灵敏度相对偏差 %+.3f%%。残差呈弯曲结构时，不能只用较高的 R² 宣称探头线性。",
            value.visible_count,
            value.point_count,
            value.sensitivity_error,
        )
    end
    bind_playback!(
        controls,
        7,
        progress,
        0:1:1000,
        [
            (point_count, 21),
            (sensitivity, DEFAULT_SENSITIVITY),
            (offset, 1.2),
            (nonlinearity, 0.30),
            (noise, 20),
            (progress, 1000),
        ];
        step = 8,
    )
    add_metrics!(metrics, values, detail)
    return figure
end

function uncertainty_model(
    repetitions,
    voltage_noise_uv,
    calibration_percent,
    current_percent,
    position_mm,
    temperature_coeff_percent_per_k,
    progress,
)
    reference_field = 50.0
    sensitivity = DEFAULT_SENSITIVITY
    full_readings = [
        reference_field + deterministic_noise(i, voltage_noise_uv / 1000.0) / sensitivity
        for i in 1:repetitions
    ]
    visible_count = clamp(floor(Int, progress / 1000 * (repetitions - 2)) + 2, 2, repetitions)
    readings = full_readings[1:visible_count]
    mean_field = sum(readings) / length(readings)
    type_a = sample_standard_deviation(readings) / sqrt(length(readings))
    voltage_component = voltage_noise_uv / 1000.0 / sensitivity / sqrt(3)
    calibration_component = reference_field * calibration_percent / 100 / sqrt(3)
    current_component = reference_field * current_percent / 100 / sqrt(3)
    position_component = 0.12 * position_mm / sqrt(3)
    temperature_component = reference_field * temperature_coeff_percent_per_k / 100 * 5.0 / sqrt(3)
    components = [
        type_a,
        voltage_component,
        calibration_component,
        current_component,
        position_component,
        temperature_component,
    ]
    combined = sqrt(sum(components .^ 2))
    expanded = 2combined
    indices = collect(1:visible_count)
    return (;
        repeat_points = Point2f.(indices, readings),
        mean_field,
        type_a,
        components,
        budget_points = Point2f.(1:6, components),
        combined,
        expanded,
        relative_expanded = 100expanded / abs(mean_field),
        visible_count,
        repetitions,
    )
end

function uncertainty_figure()
    figure, controls, metrics = base_figure()
    repeat_axis = Axis(
        figure[1, 1],
        title = "重复测量与 A 类评定",
        xlabel = "测量序号",
        ylabel = "B / mT",
    )
    budget_axis = Axis(
        figure[1, 2],
        title = "标准不确定度分量",
        xlabel = "A类  电压  标定  电流  位置  温漂",
        ylabel = "u_i(B) / mT",
        xticks = (1:6, ["A类", "电压", "标定", "电流", "位置", "温漂"]),
    )

    repetitions = add_slider!(controls, 1, "重复次数 n", 5:1:30, 12, string)
    voltage_noise = add_slider!(controls, 2, "电压噪声界限", 5:1:100, 20, value -> @sprintf("%.0f μV", value))
    calibration = add_slider!(controls, 3, "标定证书界限", 0.05:0.01:1.00, 0.30, value -> @sprintf("%.2f%%", value))
    current = add_slider!(controls, 4, "励磁电流界限", 0.05:0.01:1.00, 0.20, value -> @sprintf("%.2f%%", value))
    position = add_slider!(controls, 5, "定位误差界限", 0.1:0.1:3.0, 0.5, value -> @sprintf("%.1f mm", value))
    temperature = add_slider!(controls, 6, "灵敏度温度系数", 0.00:0.01:0.20, 0.04, value -> @sprintf("%.2f%%/K", value))
    progress = add_slider!(controls, 7, "重复采集进程", 0:1:1000, 1000, value -> @sprintf("%.1f%%", value / 10))

    data = lift(
        repetitions.value,
        voltage_noise.value,
        calibration.value,
        current.value,
        position.value,
        temperature.value,
        progress.value,
    ) do n, voltage, certificate, supply, location, drift, phase
        uncertainty_model(
            Int(n),
            Float64(voltage),
            Float64(certificate),
            Float64(supply),
            Float64(location),
            Float64(drift),
            Float64(phase),
        )
    end

    scatter!(repeat_axis, lift(value -> value.repeat_points, data), color = CYAN, markersize = 10)
    hlines!(repeat_axis, lift(value -> [value.mean_field], data), color = GREEN, linewidth = 2.3, linestyle = :dash)
    barplot!(budget_axis, 1:6, lift(value -> value.components, data), color = [CYAN, GREEN, AMBER, PINK, CYAN, GREEN])
    limits!(repeat_axis, 0.0, 31.0, 49.7, 50.3)
    limits!(budget_axis, 0.4, 6.6, 0.0, 0.35)

    values = (
        lift(value -> @sprintf("B̄ = %.4f mT", value.mean_field), data),
        lift(value -> @sprintf("u_A = %.4f mT", value.type_a), data),
        lift(value -> @sprintf("u_c = %.4f mT", value.combined), data),
        lift(value -> @sprintf("U(k=2) = %.4f mT", value.expanded), data),
    )
    detail = lift(data) do value
        @sprintf(
            "已完成 %d/%d 次；结果写作 B = (%.3f ± %.3f) mT，k=2，相对扩展不确定度 %.2f%%。各分量按独立量平方合成。",
            value.visible_count,
            value.repetitions,
            value.mean_field,
            value.expanded,
            value.relative_expanded,
        )
    end
    bind_playback!(
        controls,
        8,
        progress,
        0:1:1000,
        [
            (repetitions, 12),
            (voltage_noise, 20),
            (calibration, 0.30),
            (current, 0.20),
            (position, 0.5),
            (temperature, 0.04),
            (progress, 1000),
        ];
        step = 8,
    )
    add_metrics!(metrics, values, detail)
    return figure
end

function run_self_test()
    expected_long = MU0 * 1000 * 1.2 / 0.36
    computed_center = finite_solenoid_field(0.0, 1.2, 1000, 0.36, 0.01)
    @assert isapprox(computed_center, expected_long; rtol = 0.02)
    @assert isapprox(
        finite_solenoid_field(0.04, 1.2, 1000, 0.36, 0.06),
        finite_solenoid_field(-0.04, 1.2, 1000, 0.36, 0.06);
        rtol = 1.0e-12,
    )

    ideal_calibration = calibration_model(1.2, 10.0, DEFAULT_SENSITIVITY, 1.2, 0.0, 1000.0)
    @assert isapprox(ideal_calibration.fitted_sensitivity, DEFAULT_SENSITIVITY; rtol = 1.0e-12)
    @assert isapprox(ideal_calibration.fitted_offset, 1.2; atol = 1.0e-12)
    @assert isapprox(ideal_calibration.estimated_field, 24.0; atol = 1.0e-12)

    scan = scan_model(1.2, 1000, 0.36, 0.06, DEFAULT_SENSITIVITY, 1.2, 0.0, 0.0)
    @assert isapprox(scan.probe_field, scan.center_field; atol = 1.0e-12)
    @assert scan.uniformity >= 0

    ideal_fit = fit_model(21, DEFAULT_SENSITIVITY, 1.2, 0.0, 0.0, 1000.0)
    @assert isapprox(ideal_fit.slope, DEFAULT_SENSITIVITY; rtol = 1.0e-12)
    @assert isapprox(ideal_fit.intercept, 1.2; atol = 1.0e-12)
    @assert isapprox(ideal_fit.r_squared, 1.0; atol = 1.0e-12)

    uncertainty = uncertainty_model(12, 20.0, 0.30, 0.20, 0.5, 0.04, 1000.0)
    @assert uncertainty.combined > 0
    @assert isapprox(uncertainty.expanded, 2uncertainty.combined; rtol = 1.0e-12)

    for builder in (calibration_figure, scan_figure, fit_figure, uncertainty_figure)
        @assert builder() isa Figure
    end
    println("霍尔效应测磁场分布四个独立网页实验自检通过。")
end

const PAGE_STYLE = """
html, body { margin: 0; width: 100%; height: 100%; background: #0b0f14; color: #eef3f8; }
body { position: relative; overflow: hidden; font-family: 'Microsoft YaHei', 'Noto Sans CJK SC', sans-serif; }
.hall-effect-lab { position: absolute; left: 0; top: 0; width: $(FIGURE_WIDTH)px; height: $(FIGURE_HEIGHT)px;
    margin: 0; padding: 0; box-sizing: border-box; overflow: hidden; background: #0b0f14;
    transform-origin: 0 0; }
.hall-effect-diagnostic {
    position: fixed; left: 16px; right: 16px; bottom: 16px; z-index: 1002;
    display: none; padding: 10px 12px; color: #f7d7d7;
    background: rgba(64, 20, 28, .94); border: 1px solid rgba(255, 85, 105, .65);
    border-radius: 6px; font: 13px/1.5 ui-monospace, Consolas, monospace;
    white-space: pre-wrap;
}
.hall-effect-diagnostic.visible { display: block; }
"""

const CLIENT_STATUS_SCRIPT = """
(() => {
    let ready = false;
    const parentWindow = window.parent || window;
    const send = (type, detail = "") => parentWindow.postMessage({ type, detail }, "*");
    let fitFrame = 0;
    let layoutScale = 1;

    const syncWGLPointerScale = event => {
        const canvas = event && event.target instanceof HTMLCanvasElement ? event.target : null;
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
        const page = document.querySelector(".hall-effect-lab");
        if (!page) return;
        const viewport = window.visualViewport;
        const viewportWidth = Math.max(1, viewport ? viewport.width : (document.documentElement.clientWidth || window.innerWidth));
        const viewportHeight = Math.max(1, viewport ? viewport.height : (document.documentElement.clientHeight || window.innerHeight));
        const availableWidth = Math.max(1, viewportWidth - 12);
        const availableHeight = Math.max(1, viewportHeight - 8);
        const scale = Math.min(1.05, availableWidth / $(FIGURE_WIDTH), availableHeight / $(FIGURE_HEIGHT));
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
        fitFrame = requestAnimationFrame(() => { fitFrame = 0; fitLayout(); });
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
        document.addEventListener(eventName, syncWGLPointerScale, { capture: true, passive: true });
    }

    const showDiagnostic = detail => {
        let box = document.getElementById("hall-effect-diagnostic");
        if (!box) {
            box = document.createElement("div");
            box.id = "hall-effect-diagnostic";
            box.className = "hall-effect-diagnostic";
            document.body.appendChild(box);
        }
        box.textContent = detail;
        box.classList.add("visible");
        send("hall-effect-wgl-failed", detail);
    };
    const webglProbe = () => {
        try {
            const canvas = document.createElement("canvas");
            if (canvas.getContext("webgl2", { antialias: true })) return "webgl2";
            if (canvas.getContext("webgl", { antialias: true }) || canvas.getContext("experimental-webgl")) return "webgl1";
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
        const spinnerVisible = Boolean(spinner && spinner.getClientRects().length > 0 && getComputedStyle(spinner).visibility !== "hidden");
        if (canvas && canvas.width > 0 && canvas.height > 0 && !spinnerVisible) {
            ready = true;
            send("hall-effect-wgl-ready", glStatus);
            return;
        }
        if (!ready && performance.now() - startedAt > 75000) {
            showDiagnostic("WGLMakie/Bonito 初始化超过 75 秒。\\nWebGL 状态：" + glStatus + "\\n页面地址：" + location.href);
            return;
        }
        window.setTimeout(check, 300);
    };
    window.addEventListener("error", event => {
        showDiagnostic("浏览器脚本错误：" + event.message + "\\n" + event.filename + ":" + event.lineno);
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
            DOM.div(figure; class = "hall-effect-lab"),
            DOM.script(CLIENT_STATUS_SCRIPT),
        )
    end
end

function index_app()
    links = [
        DOM.a(name; href = path, style = "color:#73d7cf;margin-right:24px")
        for (name, path) in (
            ("霍尔电压标定", "./calibration"),
            ("沿轴磁场扫描", "./scan"),
            ("拟合与残差诊断", "./fit"),
            ("不确定度评定", "./uncertainty"),
        )
    ]
    return Bonito.App(
        DOM.div(
            DOM.style(PAGE_STYLE),
            DOM.h1("霍尔效应测磁场分布可视化实验"),
            DOM.div(links...),
            style = "padding:32px;background:#0b0f14;color:#eef3f8;min-height:100vh",
        );
        title = "霍尔效应测磁场分布可视化实验",
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
    host = get(ENV, "HALL_EFFECT_WEB_HOST", "127.0.0.1")
    port = parse(Int, get(ENV, "HALL_EFFECT_WEB_PORT", "9397"))
    proxy_url = strip(get(ENV, "HALL_EFFECT_WEB_PROXY_URL", "."))
    isempty(proxy_url) && (proxy_url = ".")
    server = Bonito.Server(host, port; proxy_url = proxy_url)
    Bonito.route!(server, "/__physics_health__" => health_app())
    Bonito.route!(server, "/" => index_app())
    Bonito.route!(server, "/calibration" => experiment_app("霍尔电压标定", calibration_figure))
    Bonito.route!(server, "/scan" => experiment_app("沿轴磁场分布扫描", scan_figure))
    Bonito.route!(server, "/fit" => experiment_app("线性拟合与残差", fit_figure))
    Bonito.route!(server, "/uncertainty" => experiment_app("不确定度评定", uncertainty_figure))
    println("霍尔效应测磁场分布网页实验已启动：http://$(host):$(port)")
    wait(server)
end

if abspath(PROGRAM_FILE) == @__FILE__
    main()
end
