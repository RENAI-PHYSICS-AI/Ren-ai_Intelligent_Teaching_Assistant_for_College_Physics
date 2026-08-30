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

const GRAVITY = 9.80665
const DEFAULT_SPHERE_DENSITY = 7800.0
const DEFAULT_LIQUID_DENSITY = 1260.0
const DEFAULT_VISCOSITY = 1.00
const FIGURE_WIDTH = 960
const FIGURE_HEIGHT = 760

const CYAN = RGBf(0.18, 0.78, 0.92)
const PINK = RGBf(0.94, 0.35, 0.50)
const AMBER = RGBf(1.00, 0.72, 0.24)
const GREEN = RGBf(0.36, 0.82, 0.55)
const VIOLET = RGBf(0.61, 0.48, 0.92)
const MUTED = RGBf(0.58, 0.62, 0.70)
const PANEL_BG = RGBf(0.075, 0.085, 0.105)
const BUTTON_BG = RGBf(0.13, 0.15, 0.19)
const CJK_PROBE_TEXT = "粘滞系数黏度落球法斯托克斯终端速度容器修正线性拟合不确定度"
const HEALTH_MARKER = "physics-experiment:viscosity"
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
        joinpath(Sys.BINDIR, "..", "share", "photoelectric", "fonts", "NotoSansCJKsc-Regular.otf"),
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

function bind_playback!(grid, row, playback_slider, playback_range, reset_values; step = 1)
    playing = Observable(false)
    playback_values = collect(playback_range)
    isempty(playback_values) && throw(ArgumentError("播放序列不能为空"))
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
    rowsize!(button_grid, 1, 31)
    rowsize!(button_grid, 2, 31)
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

sphere_volume(radius_m) = 4pi * Float64(radius_m)^3 / 3.0

function validate_fluid_inputs(radius_m, sphere_density, liquid_density, viscosity)
    Float64(radius_m) > 0 || throw(ArgumentError("小球半径必须大于零"))
    Float64(viscosity) > 0 || throw(ArgumentError("粘滞系数必须大于零"))
    Float64(liquid_density) > 0 || throw(ArgumentError("液体密度必须大于零"))
    Float64(sphere_density) > Float64(liquid_density) ||
        throw(ArgumentError("落球密度必须大于液体密度"))
    return nothing
end

function stokes_terminal_velocity(radius_m, sphere_density, liquid_density, viscosity)
    validate_fluid_inputs(radius_m, sphere_density, liquid_density, viscosity)
    return 2.0 * Float64(radius_m)^2 * GRAVITY *
           (Float64(sphere_density) - Float64(liquid_density)) /
           (9.0 * Float64(viscosity))
end

function stokes_reynolds(radius_m, speed_m_s, liquid_density, viscosity)
    return 2.0 * Float64(liquid_density) * Float64(radius_m) *
           abs(Float64(speed_m_s)) / Float64(viscosity)
end

function relaxation_time(radius_m, sphere_density, viscosity)
    mass = Float64(sphere_density) * sphere_volume(radius_m)
    return mass / (6pi * Float64(viscosity) * Float64(radius_m))
end

settling_velocity(time_s, terminal_speed, tau_s) =
    Float64(terminal_speed) * (1.0 - exp(-max(Float64(time_s), 0.0) / Float64(tau_s)))

settling_position(time_s, terminal_speed, tau_s) =
    Float64(terminal_speed) * (
        max(Float64(time_s), 0.0) -
        Float64(tau_s) * (1.0 - exp(-max(Float64(time_s), 0.0) / Float64(tau_s)))
    )

function time_at_distance(distance_m, terminal_speed, tau_s)
    distance = Float64(distance_m)
    distance >= 0 || throw(ArgumentError("下落距离不能为负"))
    distance == 0 && return 0.0
    speed = Float64(terminal_speed)
    tau = Float64(tau_s)
    speed > 0 || throw(ArgumentError("终端速度必须大于零"))
    tau > 0 || throw(ArgumentError("弛豫时间必须大于零"))
    lower = 0.0
    upper = max(distance / speed + 2 * tau, 10 * tau)
    while settling_position(upper, speed, tau) < distance
        upper *= 2.0
    end
    for _ in 1:90
        midpoint = (lower + upper) / 2.0
        if settling_position(midpoint, speed, tau) < distance
            lower = midpoint
        else
            upper = midpoint
        end
    end
    return (lower + upper) / 2.0
end

function wall_velocity_factor(lambda)
    ratio = Float64(lambda)
    0.0 <= ratio <= 0.25 || throw(ArgumentError("直径比 d/D 必须位于 0 到 0.25 之间"))
    return 1.0 - 2.1044 * ratio + 2.0888 * ratio^3 - 0.9480 * ratio^5
end

ladenburg_velocity_factor(lambda) = 1.0 / (1.0 + 2.4 * Float64(lambda))

function tanner_end_effect_status(h_over_R)
    ratio = Float64(h_over_R)
    ratio > 0.0 || throw(ArgumentError("球心到封闭端的距离比 h/R 必须大于零"))
    if ratio > 1.0
        return (;
            code = :small,
            label = "端效应较小",
            detail = "在 Tanner 的轴向 Stokes 流与常见落球管几何中，h>R 时端部附加阻力小于 Faxén 阻力的 4.5×10⁻³；这不是任意装置的通用零修正结论。",
        )
    elseif ratio > 0.30
        return (;
            code = :evaluate,
            label = "端效应需评估",
            detail = "球心已进入距封闭端一个管半径以内；Tanner 表明附加阻力会随 h/R 减小而快速增加，本页不编造连续端部修正式。",
        )
    end
    return (;
        code = :strong,
        label = "强端效应区",
        detail = "已接近 Tanner 的 h=0.25R 条件（该点端部相关阻力约为 Faxén 阻力的 1.5 倍）；应移动计时区或采用经验证的完整端部模型。",
    )
end

function stokes_model(diameter_mm, sphere_density, liquid_density, viscosity)
    radius_m = Float64(diameter_mm) * 0.5e-3
    rho_s = Float64(sphere_density)
    rho_l = Float64(liquid_density)
    eta = Float64(viscosity)
    terminal_speed = stokes_terminal_velocity(radius_m, rho_s, rho_l, eta)
    volume = sphere_volume(radius_m)
    weight = rho_s * volume * GRAVITY
    buoyancy = rho_l * volume * GRAVITY
    driving_force = weight - buoyancy
    tau_s = relaxation_time(radius_m, rho_s, eta)
    reynolds = stokes_reynolds(radius_m, terminal_speed, rho_l, eta)
    speed_values = collect(range(0.0, 1.6 * terminal_speed; length = 180))
    drag_values = 6pi * eta * radius_m .* speed_values
    time_tau = collect(range(0.0, 6.0; length = 180))
    velocity_fraction = 1.0 .- exp.(-time_tau)
    return (;
        radius_m,
        rho_s,
        rho_l,
        eta,
        terminal_speed,
        volume,
        weight,
        buoyancy,
        driving_force,
        tau_s,
        reynolds,
        speed_values,
        drag_values,
        time_tau,
        velocity_fraction,
        force_balance_error = 6pi * eta * radius_m * terminal_speed - driving_force,
    )
end

function stokes_figure()
    figure, controls, metrics = base_figure()
    response_axis = Axis(
        figure[1, 1],
        title = "从静止释放到终端速度",
        xlabel = "无量纲时间 t/τ",
        ylabel = "速度比 v/v∞",
    )
    force_axis = Axis(
        figure[1, 2],
        title = "斯托克斯阻力与有效重力",
        xlabel = "下落速度 v / mm·s⁻¹",
        ylabel = "力 / μN",
    )

    diameter = add_slider!(controls, 1, "小球直径 d", 0.8:0.1:3.0, 2.0, value -> @sprintf("%.1f mm", value))
    viscosity = add_slider!(controls, 2, "动力黏度 η", 0.20:0.05:2.00, 1.00, value -> @sprintf("%.2f Pa·s", value))
    sphere_density = add_slider!(controls, 3, "小球密度 ρs", 2500:100:8000, 7800, value -> @sprintf("%.0f kg/m³", value))
    liquid_density = add_slider!(controls, 4, "液体密度 ρl", 900:20:1400, 1260, value -> @sprintf("%.0f kg/m³", value))

    data = lift(
        diameter.value,
        sphere_density.value,
        liquid_density.value,
        viscosity.value,
    ) do d, rho_s, rho_l, eta
        stokes_model(Float64(d), Float64(rho_s), Float64(rho_l), Float64(eta))
    end

    lines!(response_axis, lift(value -> value.time_tau, data), lift(value -> value.velocity_fraction, data), color = CYAN, linewidth = 2.8, label = "v/v∞=1-exp(-t/τ)")
    hlines!(response_axis, [0.95, 0.99], color = [AMBER, GREEN], linestyle = :dash, linewidth = 1.8)
    axislegend(response_axis, position = :rb, framevisible = false, labelsize = 10)

    lines!(force_axis, lift(value -> value.speed_values .* 1000.0, data), lift(value -> value.drag_values .* 1.0e6, data), color = PINK, linewidth = 2.8, label = "Fη=6πηrv")
    hlines!(force_axis, lift(value -> [value.driving_force * 1.0e6], data), color = AMBER, linestyle = :dash, linewidth = 2.2, label = "重力-浮力")
    scatter!(force_axis, lift(value -> [value.terminal_speed * 1000.0], data), lift(value -> [value.driving_force * 1.0e6], data), color = GREEN, markersize = 16, label = "受力平衡")
    axislegend(force_axis, position = :lt, framevisible = false, labelsize = 10)

    values = (
        lift(value -> @sprintf("v∞ = %.3f mm/s", value.terminal_speed * 1000.0), data),
        lift(value -> @sprintf("Re = %.4f", value.reynolds), data),
        lift(value -> @sprintf("τ = %.3f ms", value.tau_s * 1000.0), data),
        lift(value -> @sprintf("F有效 = %.3f μN", value.driving_force * 1.0e6), data),
    )
    detail = lift(data) do value
        regime = value.reynolds < 0.1 ? "满足 Re<0.1 的蠕动流严格条件" :
                 (value.reynolds < 1.0 ? "仅近似处于低雷诺数区，应评估惯性修正" : "超出斯托克斯定律适用区")
        "Fη=6πηrv；终速时 (ρs-ρl)(4πr³/3)g=6πηrv∞，所以 η=2r²g(ρs-ρl)/(9v∞)。当前$(regime)。"
    end
    add_metrics!(metrics, values, detail)
    bind_playback!(
        controls,
        5,
        diameter,
        0.8:0.1:3.0,
        [(diameter, 2.0), (viscosity, 1.00), (sphere_density, 7800), (liquid_density, 1260)],
    )
    return figure
end

function terminal_model(
    diameter_mm,
    viscosity,
    start_distance_cm,
    measurement_distance_cm,
    timer_bias_ms;
    sphere_density = DEFAULT_SPHERE_DENSITY,
    liquid_density = DEFAULT_LIQUID_DENSITY,
)
    radius_m = Float64(diameter_mm) * 0.5e-3
    eta = Float64(viscosity)
    terminal_speed = stokes_terminal_velocity(radius_m, sphere_density, liquid_density, eta)
    tau_s = relaxation_time(radius_m, sphere_density, eta)
    start_m = Float64(start_distance_cm) * 1.0e-2
    interval_m = Float64(measurement_distance_cm) * 1.0e-2
    start_m > 0 || throw(ArgumentError("首标线距离必须大于零"))
    interval_m > 0 || throw(ArgumentError("计时区长度必须大于零"))
    first_time_s = time_at_distance(start_m, terminal_speed, tau_s)
    second_time_s = time_at_distance(start_m + interval_m, terminal_speed, tau_s)
    true_interval_s = second_time_s - first_time_s
    measured_interval_s = true_interval_s + Float64(timer_bias_ms) * 1.0e-3
    measured_interval_s > 0 || throw(ArgumentError("计时偏差使测量时间不再为正"))
    measured_speed = interval_m / measured_interval_s
    inferred_viscosity = 2.0 * radius_m^2 * GRAVITY *
                         (Float64(sphere_density) - Float64(liquid_density)) /
                         (9.0 * measured_speed)
    time_values = collect(range(0.0, max(1.04 * second_time_s, 8 * tau_s); length = 320))
    position_values = [settling_position(t, terminal_speed, tau_s) for t in time_values]
    asymptotic_positions = terminal_speed .* max.(time_values .- tau_s, 0.0)
    bias_values_ms = collect(range(-150.0, 150.0; length = 181))
    eta_by_bias = [
        2.0 * radius_m^2 * GRAVITY *
        (Float64(sphere_density) - Float64(liquid_density)) /
        (9.0 * (interval_m / (true_interval_s + bias * 1.0e-3)))
        for bias in bias_values_ms
    ]
    speed_at_first = settling_velocity(first_time_s, terminal_speed, tau_s)
    return (;
        radius_m,
        eta,
        terminal_speed,
        tau_s,
        start_m,
        interval_m,
        first_time_s,
        second_time_s,
        true_interval_s,
        measured_interval_s,
        measured_speed,
        inferred_viscosity,
        time_values,
        position_values,
        asymptotic_positions,
        bias_values_ms,
        eta_by_bias,
        selected_bias_ms = Float64(timer_bias_ms),
        speed_fraction_at_first = speed_at_first / terminal_speed,
        relative_error_percent = 100.0 * (inferred_viscosity - eta) / eta,
    )
end

function terminal_figure()
    figure, controls, metrics = base_figure()
    motion_axis = Axis(
        figure[1, 1],
        title = "落球运动与计时区",
        xlabel = "时间 t / s",
        ylabel = "下落距离 z / cm",
    )
    bias_axis = Axis(
        figure[1, 2],
        title = "计时偏差对黏度结果的影响",
        xlabel = "计时偏差 Δt / ms",
        ylabel = "η测 / Pa·s",
    )

    diameter = add_slider!(controls, 1, "小球直径 d", 0.8:0.1:3.0, 2.0, value -> @sprintf("%.1f mm", value))
    viscosity = add_slider!(controls, 2, "真实黏度 η", 0.20:0.05:2.00, 1.00, value -> @sprintf("%.2f Pa·s", value))
    start_distance = add_slider!(controls, 3, "首标线距液面", 0.2:0.2:8.0, 2.0, value -> @sprintf("%.1f cm", value))
    interval = add_slider!(controls, 4, "计时区长度 L", 5:1:25, 10, value -> @sprintf("%.0f cm", value))
    timer_bias = add_slider!(controls, 5, "计时偏差 Δt", -100:10:100, 20, value -> @sprintf("%+.0f ms", value))

    data = lift(
        diameter.value,
        viscosity.value,
        start_distance.value,
        interval.value,
        timer_bias.value,
    ) do d, eta, start_cm, length_cm, bias_ms
        terminal_model(
            Float64(d),
            Float64(eta),
            Float64(start_cm),
            Float64(length_cm),
            Float64(bias_ms),
        )
    end

    lines!(motion_axis, lift(value -> value.time_values, data), lift(value -> value.position_values .* 100.0, data), color = CYAN, linewidth = 2.8, label = "准定常单指数过渡")
    lines!(motion_axis, lift(value -> value.time_values, data), lift(value -> value.asymptotic_positions .* 100.0, data), color = AMBER, linestyle = :dash, linewidth = 2.0, label = "终速渐近直线")
    scatter!(motion_axis, lift(value -> [value.first_time_s, value.second_time_s], data), lift(value -> [value.start_m, value.start_m + value.interval_m] .* 100.0, data), color = PINK, markersize = 14, label = "两条计时标线")
    axislegend(motion_axis, position = :lt, framevisible = false, labelsize = 10)

    lines!(bias_axis, lift(value -> value.bias_values_ms, data), lift(value -> value.eta_by_bias, data), color = GREEN, linewidth = 2.8, label = "由 L/t 反演")
    hlines!(bias_axis, lift(value -> [value.eta], data), color = AMBER, linestyle = :dash, linewidth = 2.0, label = "真实黏度")
    scatter!(bias_axis, lift(value -> [value.selected_bias_ms], data), lift(value -> [value.inferred_viscosity], data), color = PINK, markersize = 16, label = "当前读数")
    axislegend(bias_axis, position = :rt, framevisible = false, labelsize = 10)

    values = (
        lift(value -> @sprintf("v(首线)/v∞ = %.6f", value.speed_fraction_at_first), data),
        lift(value -> @sprintf("计时 t = %.4f s", value.measured_interval_s), data),
        lift(value -> @sprintf("η测 = %.4f Pa·s", value.inferred_viscosity), data),
        lift(value -> @sprintf("相对误差 %+.3f%%", value.relative_error_percent), data),
    )
    detail = "教学近似由 m dv/dt=(ρs-ρl)Vg-6πηrv 得 v=v∞(1-e^{-t/τ})；它忽略 Basset 历史力与附加质量。首标线应位于加速段之后，正的反应延迟会使速度偏小、η 偏大。"
    add_metrics!(metrics, values, detail)
    bind_playback!(
        controls,
        6,
        start_distance,
        0.2:0.2:8.0,
        [(diameter, 2.0), (viscosity, 1.00), (start_distance, 2.0), (interval, 10), (timer_bias, 20)],
    )
    return figure
end

function correction_model(
    diameter_mm,
    tube_diameter_mm,
    viscosity,
    sphere_density,
    liquid_density,
    h_over_R,
)
    diameter_m = Float64(diameter_mm) * 1.0e-3
    tube_diameter_m = Float64(tube_diameter_mm) * 1.0e-3
    tube_diameter_m > diameter_m || throw(ArgumentError("容器内径必须大于小球直径"))
    lambda = diameter_m / tube_diameter_m
    lambda <= 0.25 || throw(ArgumentError("当前 d/D 超出 Faxén 级数的教学使用范围"))
    radius_m = diameter_m / 2.0
    eta = Float64(viscosity)
    terminal_unbounded = stokes_terminal_velocity(
        radius_m,
        sphere_density,
        liquid_density,
        eta,
    )
    faxen_factor = wall_velocity_factor(lambda)
    drag_factor = 1.0 / faxen_factor
    ladenburg_factor = ladenburg_velocity_factor(lambda)
    terminal_tube = terminal_unbounded * faxen_factor
    apparent_viscosity = 2.0 * radius_m^2 * GRAVITY *
                         (Float64(sphere_density) - Float64(liquid_density)) /
                         (9.0 * terminal_tube)
    corrected_viscosity = apparent_viscosity * faxen_factor
    lambda_values = collect(range(0.01, 0.22; length = 180))
    faxen_values = wall_velocity_factor.(lambda_values)
    ladenburg_values = ladenburg_velocity_factor.(lambda_values)
    apparent_bias_percent = 100.0 .* (1.0 ./ faxen_values .- 1.0)
    reynolds = stokes_reynolds(radius_m, terminal_tube, liquid_density, eta)
    end_effect_status = tanner_end_effect_status(h_over_R)
    return (;
        diameter_m,
        tube_diameter_m,
        radius_m,
        eta,
        lambda,
        terminal_unbounded,
        terminal_tube,
        faxen_factor,
        drag_factor,
        ladenburg_factor,
        apparent_viscosity,
        corrected_viscosity,
        lambda_values,
        faxen_values,
        ladenburg_values,
        apparent_bias_percent,
        reynolds,
        h_over_R = Float64(h_over_R),
        end_effect_status,
        apparent_bias_selected = 100.0 * (apparent_viscosity - eta) / eta,
    )
end

function correction_figure()
    figure, controls, metrics = base_figure()
    factor_axis = Axis(
        figure[1, 1],
        title = "圆筒壁面对终速的修正",
        xlabel = "直径比 λ=d/D",
        ylabel = "速度因子 f=v管/v∞",
    )
    bias_axis = Axis(
        figure[1, 2],
        title = "忽略壁面时的黏度高估",
        xlabel = "直径比 λ=d/D",
        ylabel = "表观黏度偏差 / %",
    )

    diameter = add_slider!(controls, 1, "小球直径 d", 1.0:0.1:4.0, 2.0, value -> @sprintf("%.1f mm", value))
    tube_diameter = add_slider!(controls, 2, "容器内径 D", 20:2:80, 40, value -> @sprintf("%.0f mm", value))
    viscosity = add_slider!(controls, 3, "真实黏度 η", 0.20:0.05:2.00, 1.00, value -> @sprintf("%.2f Pa·s", value))
    sphere_density = add_slider!(controls, 4, "小球密度 ρs", 2500:100:8000, 7800, value -> @sprintf("%.0f kg/m³", value))
    liquid_density = add_slider!(controls, 5, "液体密度 ρl", 900:20:1400, 1260, value -> @sprintf("%.0f kg/m³", value))
    end_distance = add_slider!(controls, 6, "封闭端距 h/R", 0.20:0.05:3.00, 1.50, value -> @sprintf("%.2f", value))
    for row in 1:6
        rowsize!(controls, row, 20)
    end
    rowgap!(controls, 1)

    data = lift(
        diameter.value,
        tube_diameter.value,
        viscosity.value,
        sphere_density.value,
        liquid_density.value,
        end_distance.value,
    ) do d, tube_d, eta, rho_s, rho_l, h_R
        correction_model(
            Float64(d),
            Float64(tube_d),
            Float64(eta),
            Float64(rho_s),
            Float64(rho_l),
            Float64(h_R),
        )
    end

    lines!(factor_axis, lift(value -> value.lambda_values, data), lift(value -> value.faxen_values, data), color = CYAN, linewidth = 2.8, label = "Faxén 五次式")
    lines!(factor_axis, lift(value -> value.lambda_values, data), lift(value -> value.ladenburg_values, data), color = AMBER, linestyle = :dash, linewidth = 2.2, label = "Ladenburg 近似式")
    scatter!(factor_axis, lift(value -> [value.lambda], data), lift(value -> [value.faxen_factor], data), color = PINK, markersize = 16, label = "当前装置")
    axislegend(factor_axis, position = :lb, framevisible = false, labelsize = 10)

    lines!(bias_axis, lift(value -> value.lambda_values, data), lift(value -> value.apparent_bias_percent, data), color = GREEN, linewidth = 2.8)
    scatter!(bias_axis, lift(value -> [value.lambda], data), lift(value -> [value.apparent_bias_selected], data), color = PINK, markersize = 16)

    values = (
        lift(value -> @sprintf("λ = %.4f", value.lambda), data),
        lift(value -> @sprintf("f = %.5f", value.faxen_factor), data),
        lift(value -> @sprintf("K=1/f = %.5f", value.drag_factor), data),
        lift(value -> @sprintf("h/R = %.2f · %s", value.h_over_R, value.end_effect_status.label), data),
    )
    detail = lift(data) do value
        @sprintf(
            "同轴圆筒中 v管=f(λ)v∞，f=1-2.1044λ+2.0888λ³-0.9480λ⁵，K=1/f；η表观=%.4f Pa·s，η=fη表观=%.4f Pa·s，Re=%.4f。\n端部状态：%s",
            value.apparent_viscosity,
            value.corrected_viscosity,
            value.reynolds,
            value.end_effect_status.detail,
        )
    end
    add_metrics!(metrics, values, detail)
    rowsize!(metrics, 2, 58)
    bind_playback!(
        controls,
        7,
        tube_diameter,
        20:2:80,
        [(diameter, 2.0), (tube_diameter, 40), (viscosity, 1.00), (sphere_density, 7800), (liquid_density, 1260), (end_distance, 1.50)],
    )
    return figure
end

function fit_model(
    viscosity,
    tube_diameter_mm,
    fall_distance_cm,
    timing_scatter_ms,
    diameter_uncertainty_mm;
    sphere_density = DEFAULT_SPHERE_DENSITY,
    liquid_density = DEFAULT_LIQUID_DENSITY,
)
    eta = Float64(viscosity)
    tube_diameter_m = Float64(tube_diameter_mm) * 1.0e-3
    fall_distance_m = Float64(fall_distance_cm) * 1.0e-2
    fall_distance_m > 0 || throw(ArgumentError("计时区长度必须大于零"))
    diameters_mm = collect(1.2:0.2:2.6)
    radii_m = diameters_mm .* 0.5e-3
    lambda_values = diameters_mm ./ Float64(tube_diameter_mm)
    maximum(lambda_values) <= 0.25 || throw(ArgumentError("最大球径超出壁面修正范围"))
    correction_factors = wall_velocity_factor.(lambda_values)
    unbounded_speeds = [
        stokes_terminal_velocity(radius, sphere_density, liquid_density, eta)
        for radius in radii_m
    ]
    tube_speeds = correction_factors .* unbounded_speeds
    true_times = fall_distance_m ./ tube_speeds
    pattern = [-0.72, 0.35, -0.18, 0.61, -0.47, 0.26, -0.09, 0.43]
    measured_times = true_times .+ Float64(timing_scatter_ms) * 1.0e-3 .* pattern
    all(measured_times .> 0) || throw(ArgumentError("计时散布使部分时间不再为正"))
    measured_tube_speeds = fall_distance_m ./ measured_times
    corrected_speeds = measured_tube_speeds ./ correction_factors
    radius_squared_m2 = radii_m .^ 2
    fit = linear_fit(radius_squared_m2, corrected_speeds)
    density_difference = Float64(sphere_density) - Float64(liquid_density)
    fitted_viscosity = 2.0 * GRAVITY * density_difference / (9.0 * fit.slope)

    representative_diameter_mm = sum(diameters_mm) / length(diameters_mm)
    representative_lambda = representative_diameter_mm / Float64(tube_diameter_mm)
    factor = wall_velocity_factor(representative_lambda)
    derivative = -2.1044 + 3.0 * 2.0888 * representative_lambda^2 -
                 5.0 * 0.9480 * representative_lambda^4
    logarithmic_f_sensitivity = representative_lambda * derivative / factor
    regression_relative = abs(fit.slope_uncertainty / fit.slope)
    diameter_relative = abs(2.0 + logarithmic_f_sensitivity) *
                        Float64(diameter_uncertainty_mm) / representative_diameter_mm
    length_relative = 0.5e-3 / fall_distance_m
    density_relative = hypot(5.0, 1.0) / density_difference
    tube_relative = abs(logarithmic_f_sensitivity) * 0.1 / Float64(tube_diameter_mm)
    component_labels = ["拟合", "球径", "测距", "密度差", "管径"]
    component_relative = [
        regression_relative,
        diameter_relative,
        length_relative,
        density_relative,
        tube_relative,
    ]
    combined_relative = sqrt(sum(abs2, component_relative))
    residual_rms = sqrt(sum(abs2, fit.residuals) / length(fit.residuals))
    residual_max_abs = maximum(abs, fit.residuals)
    return (;
        eta,
        tube_diameter_m,
        fall_distance_m,
        diameters_mm,
        radii_m,
        lambda_values,
        correction_factors,
        unbounded_speeds,
        tube_speeds,
        true_times,
        measured_times,
        measured_tube_speeds,
        corrected_speeds,
        radius_squared_m2,
        fit,
        fitted_viscosity,
        component_labels,
        component_indices = collect(1:length(component_labels)),
        component_relative,
        component_percent = 100.0 .* component_relative,
        combined_relative,
        residual_rms,
        residual_max_abs,
        viscosity_uncertainty = fitted_viscosity * combined_relative,
        relative_error_percent = 100.0 * (fitted_viscosity - eta) / eta,
    )
end

function fit_figure()
    figure, controls, metrics = base_figure()
    fit_axis = Axis(
        figure[1, 1],
        title = "壁面修正后的多球线性拟合",
        xlabel = "球半径平方 r² / mm²",
        ylabel = "修正速度 v∞=v管/f / mm·s⁻¹",
    )
    budget_axis = Axis(
        figure[1, 2],
        title = "相对标准不确定度分量",
        xlabel = "输入量",
        ylabel = "相对分量 / %",
        xticks = (collect(1:5), ["拟合", "d", "L", "Δρ", "D"]),
    )

    viscosity = add_slider!(controls, 1, "真实黏度 η", 0.40:0.05:1.80, 1.00, value -> @sprintf("%.2f Pa·s", value))
    tube_diameter = add_slider!(controls, 2, "容器内径 D", 25:1:60, 40, value -> @sprintf("%.0f mm", value))
    fall_distance = add_slider!(controls, 3, "计时区长度 L", 8:1:20, 12, value -> @sprintf("%.0f cm", value))
    timing_scatter = add_slider!(controls, 4, "计时散布", 0:5:100, 30, value -> @sprintf("%.0f ms", value))
    diameter_u = add_slider!(controls, 5, "球径 u(d)", 0.002:0.002:0.020, 0.010, value -> @sprintf("%.3f mm", value))

    data = lift(
        viscosity.value,
        tube_diameter.value,
        fall_distance.value,
        timing_scatter.value,
        diameter_u.value,
    ) do eta, tube_d, length_cm, scatter_ms, u_d
        fit_model(
            Float64(eta),
            Float64(tube_d),
            Float64(length_cm),
            Float64(scatter_ms),
            Float64(u_d),
        )
    end

    scatter!(fit_axis, lift(value -> value.radius_squared_m2 .* 1.0e6, data), lift(value -> value.corrected_speeds .* 1000.0, data), color = CYAN, markersize = 13, label = "修正测量值")
    lines!(fit_axis, lift(value -> value.radius_squared_m2 .* 1.0e6, data), lift(value -> value.fit.predicted .* 1000.0, data), color = GREEN, linewidth = 2.8, label = "v=a r²+b（自由截距）")
    axislegend(fit_axis, position = :lt, framevisible = false, labelsize = 10)

    barplot!(budget_axis, lift(value -> value.component_indices, data), lift(value -> value.component_percent, data), color = [CYAN, PINK, AMBER, GREEN, VIOLET])

    values = (
        lift(value -> @sprintf("η拟合 = %.4f Pa·s", value.fitted_viscosity), data),
        lift(value -> @sprintf("R² = %.6f", value.fit.r_squared), data),
        lift(value -> @sprintf("残差 RMS/max = %.2f/%.2f μm/s", value.residual_rms * 1.0e6, value.residual_max_abs * 1.0e6), data),
        lift(value -> @sprintf("uᵣ(η) = %.3f%%", value.combined_relative * 100.0), data),
    )
    detail = lift(data) do value
        @sprintf(
            "先用 Faxén 速度因子 f 将 v管 修正为 v∞，再自由截距拟合 v∞=a r²+b；η=(%.4f±%.4f) Pa·s（k=1），截距=%+.3f mm/s，相对偏差 %+.3f%%。\n残差 RMS=%.2f μm/s，max|e|=%.2f μm/s；应结合残差随 r² 的结构判断模型，而不能只看 R²。\n预算固定标准不确定度假设：u(L)=0.5 mm、u(ρs)=5 kg/m³、u(ρl)=1 kg/m³、u(D)=0.1 mm；u(d) 可调，计时散布由拟合斜率不确定度计入。",
            value.fitted_viscosity,
            value.viscosity_uncertainty,
            value.fit.intercept * 1000.0,
            value.relative_error_percent,
            value.residual_rms * 1.0e6,
            value.residual_max_abs * 1.0e6,
        )
    end
    add_metrics!(metrics, values, detail)
    rowsize!(metrics, 2, 68)
    bind_playback!(
        controls,
        6,
        viscosity,
        0.40:0.05:1.80,
        [(viscosity, 1.00), (tube_diameter, 40), (fall_distance, 12), (timing_scatter, 30), (diameter_u, 0.010)],
    )
    return figure
end

function run_self_test()
    stokes = stokes_model(2.0, 7800.0, 1260.0, 1.0)
    @assert stokes.terminal_speed > 0.0
    @assert stokes.reynolds < 0.1
    @assert abs(stokes.force_balance_error) < 1.0e-18
    @assert isapprox(
        6pi * stokes.eta * stokes.radius_m * stokes.terminal_speed,
        stokes.driving_force;
        rtol = 1.0e-13,
    )

    terminal = terminal_model(2.0, 1.0, 2.0, 10.0, 0.0)
    @assert terminal.second_time_s > terminal.first_time_s > 0.0
    @assert terminal.speed_fraction_at_first > 0.999
    @assert isapprox(terminal.inferred_viscosity, 1.0; rtol = 1.0e-10)
    @assert isapprox(
        settling_position(terminal.first_time_s, terminal.terminal_speed, terminal.tau_s),
        terminal.start_m;
        rtol = 1.0e-11,
    )

    correction = correction_model(2.0, 40.0, 1.0, 7800.0, 1260.0, 1.5)
    @assert 0.0 < correction.faxen_factor < 1.0
    @assert correction.drag_factor > 1.0
    @assert correction.terminal_tube < correction.terminal_unbounded
    @assert correction.apparent_viscosity > correction.eta
    @assert isapprox(correction.corrected_viscosity, correction.eta; rtol = 1.0e-13)
    @assert correction.reynolds < 0.1
    @assert correction.end_effect_status.code == :small
    @assert tanner_end_effect_status(0.25).code == :strong

    fitted = fit_model(1.0, 40.0, 12.0, 0.0, 0.010)
    @assert fitted.fit.slope > 0.0
    @assert fitted.fit.r_squared > 0.999999999
    @assert abs(fitted.fit.intercept) < 1.0e-12
    @assert isapprox(fitted.fitted_viscosity, 1.0; rtol = 1.0e-11)
    @assert fitted.combined_relative > 0.0
    @assert fitted.viscosity_uncertainty > 0.0
    @assert fitted.residual_rms < 1.0e-12
    @assert fitted.residual_max_abs < 1.0e-12

    noisy = fit_model(1.0, 40.0, 12.0, 40.0, 0.010)
    @assert noisy.fit.slope_uncertainty > 0.0
    @assert noisy.combined_relative > fitted.combined_relative

    for builder in (stokes_figure, terminal_figure, correction_figure, fit_figure)
        @assert builder() isa Figure
    end
    println("粘滞系数四个独立网页实验自检通过：斯托克斯定律、终速计时、容器修正及多球拟合均正常。")
end

const PAGE_STYLE = """
html, body { margin: 0; width: 100%; height: 100%; background: #0b0f14; color: #eef3f8; }
body { position: relative; overflow: hidden; font-family: 'Microsoft YaHei', 'Noto Sans CJK SC', sans-serif; }
.viscosity-lab { position: absolute; left: 0; top: 0; width: $(FIGURE_WIDTH)px; height: $(FIGURE_HEIGHT)px;
    margin: 0; padding: 0; box-sizing: border-box; overflow: hidden; background: #0b0f14;
    transform-origin: 0 0; }
.viscosity-diagnostic {
    position: fixed; left: 16px; right: 16px; bottom: 16px; z-index: 1002;
    display: none; padding: 10px 12px; color: #f7d7d7;
    background: rgba(64, 20, 28, .94); border: 1px solid rgba(255, 85, 105, .65);
    border-radius: 6px; font: 13px/1.5 ui-monospace, Consolas, monospace;
    white-space: pre-wrap;
}
.viscosity-diagnostic.visible { display: block; }
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
        const page = document.querySelector(".viscosity-lab");
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
        let box = document.getElementById("viscosity-diagnostic");
        if (!box) {
            box = document.createElement("div");
            box.id = "viscosity-diagnostic";
            box.className = "viscosity-diagnostic";
            document.body.appendChild(box);
        }
        box.textContent = detail;
        box.classList.add("visible");
        send("viscosity-wgl-failed", detail);
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
            send("viscosity-wgl-ready", glStatus);
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
            DOM.div(figure; class = "viscosity-lab"),
            DOM.script(CLIENT_STATUS_SCRIPT),
        )
    end
end

function index_app()
    links = [
        DOM.a(name; href = path, style = "color:#73d7cf;margin-right:24px")
        for (name, path) in (
            ("斯托克斯定律与受力平衡", "./stokes"),
            ("终端速度与落球计时", "./terminal"),
            ("容器壁面修正", "./correction"),
            ("多球拟合与不确定度", "./fit"),
        )
    ]
    return Bonito.App(
        DOM.div(
            DOM.style(PAGE_STYLE),
            DOM.h1("粘滞系数测定（落球法）"),
            DOM.div(links...),
            style = "padding:32px;background:#0b0f14;color:#eef3f8;min-height:100vh",
        );
        title = "粘滞系数测定（落球法）",
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
    host = get(ENV, "VISCOSITY_WEB_HOST", "127.0.0.1")
    port = parse(Int, get(ENV, "VISCOSITY_WEB_PORT", "9392"))
    proxy_url = strip(get(ENV, "VISCOSITY_WEB_PROXY_URL", "."))
    isempty(proxy_url) && (proxy_url = ".")
    server = Bonito.Server(host, port; proxy_url = proxy_url)
    Bonito.route!(server, "/__physics_health__" => health_app())
    Bonito.route!(server, "/" => index_app())
    Bonito.route!(server, "/stokes" => experiment_app("斯托克斯定律与受力平衡", stokes_figure))
    Bonito.route!(server, "/terminal" => experiment_app("终端速度与落球计时", terminal_figure))
    Bonito.route!(server, "/correction" => experiment_app("容器壁面修正", correction_figure))
    Bonito.route!(server, "/fit" => experiment_app("多球拟合与不确定度", fit_figure))
    println("粘滞系数网页实验已启动：http://$(host):$(port)")
    wait(server)
end

if abspath(PROGRAM_FILE) == @__FILE__
    main()
end
