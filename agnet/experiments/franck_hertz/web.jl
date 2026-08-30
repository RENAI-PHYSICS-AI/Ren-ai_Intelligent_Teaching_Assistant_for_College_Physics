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

const FIGURE_WIDTH = 960
const FIGURE_HEIGHT = 760
const MERCURY_EXCITATION_EV = 4.89
const HC_EV_NM = 1239.8419843320026
const CYAN = RGBf(0.18, 0.78, 0.92)
const PINK = RGBf(0.94, 0.35, 0.50)
const AMBER = RGBf(1.00, 0.72, 0.24)
const GREEN = RGBf(0.36, 0.82, 0.55)
const VIOLET = RGBf(0.61, 0.48, 0.92)
const MUTED = RGBf(0.58, 0.62, 0.70)
const PANEL_BG = RGBf(0.075, 0.085, 0.105)
const BUTTON_BG = RGBf(0.13, 0.15, 0.19)
const CJK_PROBE_TEXT = "弗兰克赫兹汞原子电子非弹性碰撞激发电势拒斥场收集电流不确定度"
const HEALTH_MARKER = "physics-experiment:franck-hertz"
const SAFETY_TEXT = "安全：本页仅作数值仿真。真实汞管实验涉及有毒汞蒸气、高温和高压（包括高温玻璃表面与高压电源），只能使用完好封装设备并按实验室规程操作。"
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
    rowsize!(figure.layout, 1, 360)
    rowsize!(figure.layout, 2, 158)
    rowsize!(figure.layout, 3, 125)
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
    rowsize!(grid, row, 21)
    rowgap!(grid, 3)
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
    Label(
        grid[3, 1:4],
        SAFETY_TEXT,
        color = RGBf(0.96, 0.56, 0.56),
        halign = :left,
        fontsize = 11.5,
        tellwidth = false,
    )
    rowsize!(grid, 1, 28)
    rowsize!(grid, 2, 52)
    rowsize!(grid, 3, 24)
    rowgap!(grid, 5)
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
    length(x) >= 3 || throw(ArgumentError("线性拟合至少需要三个点"))
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

excitation_wavelength_nm(excitation_ev) = HC_EV_NM / Float64(excitation_ev)

function sample_standard_deviation(values)
    data = Float64.(values)
    length(data) >= 2 || return 0.0
    mean_value = sum(data) / length(data)
    return sqrt(sum(abs2, data .- mean_value) / (length(data) - 1))
end

function apparatus_model(accelerating_voltage, retarding_voltage, contact_potential, oven_temperature, excitation_ev)
    ua = Float64(accelerating_voltage)
    ur = Float64(retarding_voltage)
    uk = Float64(contact_potential)
    temperature = Float64(oven_temperature)
    excitation = Float64(excitation_ev)
    ua >= 0 || throw(ArgumentError("加速电压不能为负"))
    ur >= 0 || throw(ArgumentError("拒斥电压不能为负"))
    uk >= 0 || throw(ArgumentError("接触电势差不能为负"))
    temperature > 0 || throw(ArgumentError("炉温必须大于绝对零度"))
    excitation > 0 || throw(ArgumentError("激发电势必须大于零"))
    effective_voltage = max(ua - uk, 0.0)
    collision_count = floor(Int, effective_voltage / excitation)
    residual_energy = effective_voltage - collision_count * excitation
    collector_margin = residual_energy - ur
    collected = collector_margin > 0
    x_curve = collect(range(0.08, 0.78; length = 361))
    fraction = (x_curve .- 0.08) ./ 0.70
    total_gain = effective_voltage .* fraction
    energy_curve = mod.(total_gain, excitation)
    collision_positions = if collision_count == 0 || effective_voltage == 0
        Float64[]
    else
        [0.08 + 0.70 * n * excitation / effective_voltage for n in 1:collision_count]
    end
    potential_x = [0.08, 0.78, 0.90]
    potential_y = [0.0, ua, ua - ur]
    pressure_factor = exp(0.055 * (temperature - 180.0))
    return (;
        ua,
        ur,
        uk,
        temperature,
        excitation,
        effective_voltage,
        collision_count,
        residual_energy,
        collector_margin,
        collected,
        x_curve,
        energy_curve,
        collision_positions,
        potential_x,
        potential_y,
        pressure_factor,
        wavelength_nm = excitation_wavelength_nm(excitation),
    )
end

function apparatus_figure()
    figure, controls, metrics = base_figure()
    tube_axis = Axis(
        figure[1, 1],
        title = "加速区、栅极与拒斥场",
        xlabel = "管内相对位置",
        ylabel = "电势 V / V",
        limits = ((0.0, 1.0), (-4.0, 66.0)),
    )
    energy_axis = Axis(
        figure[1, 2],
        title = "电子动能与汞能级参照",
        xlabel = "阴极 → 栅极",
        ylabel = "动能 Eₖ / eV",
        limits = ((0.0, 1.0), (-0.5, 10.0)),
    )

    accelerating = add_slider!(controls, 1, "加速电压 Uₐ", 0:1:60, 28, value -> @sprintf("%.0f V", value))
    retarding = add_slider!(controls, 2, "拒斥电压 Uᵣ", 0.0:0.1:3.0, 1.5, value -> @sprintf("%.1f V", value))
    contact = add_slider!(controls, 3, "接触电势差 Uₖ", 0.0:0.1:3.0, 1.2, value -> @sprintf("%.1f V", value))
    temperature = add_slider!(controls, 4, "炉温 T", 150:2:200, 180, value -> @sprintf("%.0f ℃", value))
    excitation = add_slider!(controls, 5, "有效激发电势 U₁", 4.70:0.01:5.10, MERCURY_EXCITATION_EV, value -> @sprintf("%.2f V", value))

    data = lift(accelerating.value, retarding.value, contact.value, temperature.value, excitation.value) do ua, ur, uk, temp, u1
        apparatus_model(Float64(ua), Float64(ur), Float64(uk), Float64(temp), Float64(u1))
    end

    lines!(tube_axis, lift(value -> value.potential_x, data), lift(value -> value.potential_y, data), color = CYAN, linewidth = 3.0, label = "管内电势")
    vlines!(tube_axis, [0.08], color = AMBER, linewidth = 3.0, label = "阴极 K")
    vlines!(tube_axis, [0.78], color = GREEN, linewidth = 3.0, label = "栅极 G")
    vlines!(tube_axis, [0.90], color = PINK, linewidth = 3.0, label = "收集极 A")
    axislegend(tube_axis, position = :lt, framevisible = false, labelsize = 9)

    lines!(energy_axis, lift(value -> value.x_curve, data), lift(value -> value.energy_curve, data), color = PINK, linewidth = 2.8, label = "电子剩余动能")
    hlines!(energy_axis, [4.67], color = VIOLET, linestyle = :dot, linewidth = 1.5, label = "6³P₀ 4.67 eV")
    hlines!(energy_axis, lift(value -> [value.excitation], data), color = AMBER, linestyle = :dash, linewidth = 2.0, label = "设定有效激发能")
    hlines!(energy_axis, [6.70], color = MUTED, linestyle = :dot, linewidth = 1.5, label = "6¹P₁ 6.70 eV")
    scatter!(energy_axis, lift(value -> value.collision_positions, data), lift(value -> fill(0.0, length(value.collision_positions)), data), color = GREEN, marker = :diamond, markersize = 13, label = "非弹性碰撞")
    axislegend(energy_axis, position = :rt, framevisible = false, labelsize = 9)

    values = (
        lift(value -> @sprintf("有效加速电势 = %.2f V", value.effective_voltage), data),
        lift(value -> @sprintf("激发碰撞 = %d 次", value.collision_count), data),
        lift(value -> @sprintf("收集能量余量 = %.2f eV", value.collector_margin), data),
        lift(value -> value.collected ? "电子可到达收集极" : "电子被拒斥场挡回", data),
    )
    detail = lift(data) do value
        @sprintf(
            "加速区内 e(Uₐ-Uₖ)转化为电子动能；每次非弹性碰撞损失约 eU₁。穿过栅极后若 Eₖ>eUᵣ，电子才能到达收集极。\n汞共振激发约 4.89 eV，对应 253.6 nm 谱线；6³P₀ 亚稳态约 4.67 eV。当前仿真设定 U₁=%.2f V，由 λ=hc/(eΔU) 得 %.1f nm；相对蒸气密度因子 %.2f。",
            value.excitation,
            value.wavelength_nm,
            value.pressure_factor,
        )
    end
    add_metrics!(metrics, values, detail)
    bind_playback!(
        controls,
        6,
        accelerating,
        0:1:60,
        [(accelerating, 28), (retarding, 1.5), (contact, 1.2), (temperature, 180), (excitation, MERCURY_EXCITATION_EV)],
    )
    return figure
end

function franck_hertz_curve(excitation_ev, contact_potential, retarding_voltage, oven_temperature, noise_level)
    excitation = Float64(excitation_ev)
    contact = Float64(contact_potential)
    retarding = Float64(retarding_voltage)
    temperature = Float64(oven_temperature)
    noise = Float64(noise_level)
    excitation > 0 || throw(ArgumentError("激发电势必须大于零"))
    contact >= 0 || throw(ArgumentError("接触电势差不能为负"))
    retarding >= 0 || throw(ArgumentError("拒斥电压不能为负"))
    noise >= 0 || throw(ArgumentError("噪声幅度不能为负"))
    voltages = collect(range(0.0, 60.0; length = 601))
    first_peak = contact + retarding + excitation
    peak_positions = collect(first_peak:excitation:60.0)
    sigma = 0.42 + 0.0009 * (temperature - 178.0)^2 + 0.35 * noise
    pressure_gain = exp(-((temperature - 178.0) / 30.0)^2)
    noise_pattern = [sin(0.73 * i) + 0.45 * sin(2.17 * i + 0.4) for i in eachindex(voltages)]
    currents = Float64[]
    for (i, voltage) in enumerate(voltages)
        background = 0.10 + 0.010 * voltage
        peaks = sum(
            (1.2 + 0.035 * position) * exp(-0.5 * ((voltage - position) / sigma)^2)
            for position in peak_positions
        )
        push!(currents, max(0.0, background + pressure_gain * peaks + 0.055 * noise * noise_pattern[i]))
    end
    derivative_voltage = 0.5 .* (voltages[1:end-1] .+ voltages[2:end])
    derivative = diff(currents) ./ diff(voltages)
    mean_spacing = length(peak_positions) >= 2 ? sum(diff(peak_positions)) / (length(peak_positions) - 1) : NaN
    return (;
        excitation,
        contact,
        retarding,
        temperature,
        noise,
        sigma,
        pressure_gain,
        voltages,
        currents,
        derivative_voltage,
        derivative,
        peak_positions,
        mean_spacing,
        wavelength_nm = excitation_wavelength_nm(excitation),
    )
end

function curve_figure()
    figure, controls, metrics = base_figure()
    current_axis = Axis(
        figure[1, 1],
        title = "汞管收集电流—加速电压曲线",
        xlabel = "加速电压 Uₐ / V",
        ylabel = "收集电流 Iₐ / 任意单位",
        limits = ((0.0, 60.0), (0.0, 4.2)),
    )
    derivative_axis = Axis(
        figure[1, 2],
        title = "峰谷位置的导数识别",
        xlabel = "加速电压 Uₐ / V",
        ylabel = "dIₐ/dUₐ / 任意单位",
        limits = ((0.0, 60.0), (-4.0, 4.0)),
    )

    excitation = add_slider!(controls, 1, "有效激发电势 U₁", 4.70:0.01:5.10, MERCURY_EXCITATION_EV, value -> @sprintf("%.2f V", value))
    contact = add_slider!(controls, 2, "接触电势差 Uₖ", 0.0:0.1:3.0, 1.2, value -> @sprintf("%.1f V", value))
    retarding = add_slider!(controls, 3, "拒斥电压 Uᵣ", 0.5:0.1:3.0, 1.5, value -> @sprintf("%.1f V", value))
    temperature = add_slider!(controls, 4, "炉温 T", 150:2:200, 178, value -> @sprintf("%.0f ℃", value))
    noise = add_slider!(controls, 5, "电流噪声", 0.0:0.1:1.0, 0.2, value -> @sprintf("%.1f", value))

    data = lift(excitation.value, contact.value, retarding.value, temperature.value, noise.value) do u1, uk, ur, temp, eta
        franck_hertz_curve(Float64(u1), Float64(uk), Float64(ur), Float64(temp), Float64(eta))
    end

    lines!(current_axis, lift(value -> value.voltages, data), lift(value -> value.currents, data), color = CYAN, linewidth = 2.8, label = "Iₐ(Uₐ)")
    vlines!(current_axis, lift(value -> value.peak_positions, data), color = (AMBER, 0.55), linestyle = :dash, linewidth = 1.4, label = "理论峰位")
    axislegend(current_axis, position = :lt, framevisible = false, labelsize = 9)
    lines!(derivative_axis, lift(value -> value.derivative_voltage, data), lift(value -> value.derivative, data), color = PINK, linewidth = 2.3)
    hlines!(derivative_axis, [0.0], color = (MUTED, 0.65), linewidth = 1.2)

    values = (
        lift(value -> @sprintf("峰数 = %d", length(value.peak_positions)), data),
        lift(value -> @sprintf("平均间距 ΔU = %.3f V", value.mean_spacing), data),
        lift(value -> @sprintf("峰宽 σ = %.3f V", value.sigma), data),
        lift(value -> @sprintf("λ = %.1f nm", value.wavelength_nm), data),
    )
    detail = lift(data) do value
        @sprintf(
            "相邻峰（或谷）的加速电压间隔满足 ΔU≈U₁；Uₖ 与 Uᵣ 主要平移曲线，不改变理想峰间距。\n本页为说明峰谷周期的现象模型；炉温 %.0f ℃ 时碰撞宽化因子 σ=%.3f V，实验定量结果应由实测峰位拟合得出。",
            value.temperature,
            value.sigma,
        )
    end
    add_metrics!(metrics, values, detail)
    bind_playback!(
        controls,
        6,
        excitation,
        4.70:0.01:5.10,
        [(excitation, MERCURY_EXCITATION_EV), (contact, 1.2), (retarding, 1.5), (temperature, 178), (noise, 0.2)],
    )
    return figure
end

const PEAK_NOISE_PATTERN = [0.00, 0.58, -0.42, 0.31, -0.51, 0.22, 0.47, -0.28, 0.13, -0.37]

function peak_analysis_model(excitation_ev, peak_count, contact_potential, voltage_scale_percent, peak_noise, nonlinearity)
    excitation = Float64(excitation_ev)
    count = clamp(round(Int, peak_count), 4, 10)
    contact = Float64(contact_potential)
    scale = 1.0 + Float64(voltage_scale_percent) / 100.0
    noise = Float64(peak_noise)
    curvature = Float64(nonlinearity)
    excitation > 0 || throw(ArgumentError("激发电势必须大于零"))
    contact >= 0 || throw(ArgumentError("接触电势差不能为负"))
    noise >= 0 || throw(ArgumentError("峰位读数散布不能为负"))
    indices = collect(1:count)
    center = (count + 1) / 2
    true_positions = contact .+ 1.5 .+ excitation .* indices
    measured_positions = scale .* true_positions .+ noise .* PEAK_NOISE_PATTERN[1:count] .+ curvature .* ((indices .- center) .^ 2) ./ count
    fit = linear_fit(indices, measured_positions)
    fitted_excitation = fit.slope
    wavelength_nm = excitation_wavelength_nm(fitted_excitation)
    adjacent_spacings = diff(measured_positions)
    spacing_mean = sum(adjacent_spacings) / length(adjacent_spacings)
    spacing_standard_deviation = sample_standard_deviation(adjacent_spacings)
    return (;
        excitation,
        count,
        contact,
        scale,
        noise,
        curvature,
        indices,
        true_positions,
        measured_positions,
        fit,
        fitted_excitation,
        wavelength_nm,
        adjacent_indices = collect(1:length(adjacent_spacings)),
        adjacent_spacings,
        spacing_mean,
        spacing_standard_deviation,
        relative_error_percent = 100.0 * (fitted_excitation - excitation) / excitation,
    )
end

function analysis_figure()
    figure, controls, metrics = base_figure()
    fit_axis = Axis(
        figure[1, 1],
        title = "峰位序列线性拟合",
        xlabel = "峰序号 n",
        ylabel = "峰位 Uₙ / V",
        limits = ((0.5, 10.5), (0.0, 56.0)),
    )
    spacing_axis = Axis(
        figure[1, 2],
        title = "相邻峰间距检查",
        xlabel = "峰对 n → n+1",
        ylabel = "ΔUₙ / V",
        limits = ((0.5, 9.5), (4.2, 5.6)),
    )

    excitation = add_slider!(controls, 1, "标称激发电势 U₁", 4.70:0.01:5.10, MERCURY_EXCITATION_EV, value -> @sprintf("%.2f V", value))
    peak_count = add_slider!(controls, 2, "可识别峰数 N", 4:1:10, 8, value -> @sprintf("%.0f 个", value))
    contact = add_slider!(controls, 3, "接触电势差 Uₖ", 0.0:0.1:3.0, 1.2, value -> @sprintf("%.1f V", value))
    scale_error = add_slider!(controls, 4, "电压标度偏差", -1.0:0.1:1.0, 0.0, value -> @sprintf("%+.1f%%", value))
    peak_noise = add_slider!(controls, 5, "峰位读数散布", 0.00:0.01:0.20, 0.06, value -> @sprintf("%.2f V", value))
    nonlinearity = add_slider!(controls, 6, "扫描非线性", -0.10:0.01:0.10, 0.00, value -> @sprintf("%+.2f V", value))

    data = lift(excitation.value, peak_count.value, contact.value, scale_error.value, peak_noise.value, nonlinearity.value) do u1, count, uk, scale, noise, curve
        peak_analysis_model(Float64(u1), Float64(count), Float64(uk), Float64(scale), Float64(noise), Float64(curve))
    end

    scatter!(fit_axis, lift(value -> value.indices, data), lift(value -> value.measured_positions, data), color = CYAN, markersize = 13, label = "实测峰位")
    lines!(fit_axis, lift(value -> value.indices, data), lift(value -> value.fit.predicted, data), color = GREEN, linewidth = 2.8, label = "Uₙ=b+nU₁")
    axislegend(fit_axis, position = :lt, framevisible = false, labelsize = 9)
    scatterlines!(spacing_axis, lift(value -> value.adjacent_indices, data), lift(value -> value.adjacent_spacings, data), color = PINK, markersize = 12, linewidth = 2.2)
    hlines!(spacing_axis, lift(value -> [value.spacing_mean], data), color = AMBER, linestyle = :dash, linewidth = 2.0)

    values = (
        lift(value -> @sprintf("U₁,拟合 = %.4f V", value.fitted_excitation), data),
        lift(value -> @sprintf("截距 b = %.3f V", value.fit.intercept), data),
        lift(value -> @sprintf("λ = %.2f nm", value.wavelength_nm), data),
        lift(value -> @sprintf("R² = %.6f", value.fit.r_squared), data),
    )
    detail = lift(data) do value
        @sprintf(
            "用 Uₙ=b+nΔU 作自由截距线性拟合，斜率给出有效激发电势，再由 λ=hc/(eΔU)≈1239.84/ΔU nm 换算谱线波长。\n常量接触电势差和拒斥电压的共同偏置进入截距，不改变斜率；绝对首峰不应直接当作激发电势。当前相邻峰平均 %.4f V，标准差 %.4f V，拟合相对偏差 %+.3f%%。",
            value.spacing_mean,
            value.spacing_standard_deviation,
            value.relative_error_percent,
        )
    end
    add_metrics!(metrics, values, detail)
    bind_playback!(
        controls,
        7,
        peak_count,
        4:1:10,
        [(excitation, MERCURY_EXCITATION_EV), (peak_count, 8), (contact, 1.2), (scale_error, 0.0), (peak_noise, 0.06), (nonlinearity, 0.00)],
    )
    return figure
end

const REPEAT_PATTERN = [-1.18, 0.42, 0.91, -0.36, 1.32, -0.74, 0.18, 0.67, -1.01, 1.08, -0.22, 0.51]
const CONTACT_PATTERN = [0.52, -0.31, 0.18, -0.47, 0.38, -0.16, 0.27, -0.42, 0.11, 0.34, -0.25, 0.07]

function uncertainty_model(repetitions, oven_temperature, temperature_uncertainty, peak_noise, contact_drift, calibration_percent)
    count = clamp(round(Int, repetitions), 3, 12)
    temperature = Float64(oven_temperature)
    u_temperature_setting = Float64(temperature_uncertainty)
    reading_noise = Float64(peak_noise)
    drift = Float64(contact_drift)
    calibration = Float64(calibration_percent) / 100.0
    all(value -> value >= 0, (u_temperature_setting, reading_noise, drift, calibration)) ||
        throw(ArgumentError("不确定度输入不能为负"))
    thermal_broadening = 0.018 + 0.00011 * (temperature - 178.0)^2
    repeat_scale = sqrt(thermal_broadening^2 + (reading_noise / sqrt(7.0))^2)
    estimates = MERCURY_EXCITATION_EV .+
        repeat_scale .* REPEAT_PATTERN[1:count] .+
        0.20 * drift .* CONTACT_PATTERN[1:count]
    mean_excitation = sum(estimates) / count
    repeat_standard_deviation = sample_standard_deviation(estimates)
    u_type_a = repeat_standard_deviation / sqrt(count)
    u_peak = reading_noise / sqrt(12.0 * 42.0)
    u_contact = drift / sqrt(12.0)
    temperature_sensitivity = 0.0008 # V/K，表征峰形随汞蒸气密度的敏感性
    u_temperature = temperature_sensitivity * u_temperature_setting
    u_calibration = mean_excitation * calibration / sqrt(3.0)
    components = [u_type_a, u_peak, u_contact, u_temperature, u_calibration]
    combined = sqrt(sum(abs2, components))
    expanded = 2.0 * combined
    wavelength_nm = excitation_wavelength_nm(mean_excitation)
    wavelength_uncertainty_nm = wavelength_nm * combined / mean_excitation
    return (;
        count,
        temperature,
        u_temperature_setting,
        reading_noise,
        drift,
        calibration,
        thermal_broadening,
        repeat_indices = collect(1:count),
        estimates,
        mean_excitation,
        sample_standard_deviation = repeat_standard_deviation,
        component_indices = collect(1:5),
        component_labels = ["A类", "峰位", "Uₖ漂移", "炉温", "电压标定"],
        components,
        combined,
        expanded,
        wavelength_nm,
        wavelength_uncertainty_nm,
    )
end

function uncertainty_figure()
    figure, controls, metrics = base_figure()
    repeat_axis = Axis(
        figure[1, 1],
        title = "重复扫描得到的激发电势",
        xlabel = "测量序号",
        ylabel = "U₁ / V",
        limits = ((0.5, 12.5), (4.65, 5.13)),
    )
    budget_axis = Axis(
        figure[1, 2],
        title = "U₁ 标准不确定度分量",
        xlabel = "来源",
        ylabel = "u / V",
        xticks = (collect(1:5), ["A类", "峰位", "Uₖ漂移", "T", "标定"]),
        limits = ((0.5, 5.5), (0.0, 0.12)),
    )

    repetitions = add_slider!(controls, 1, "重复扫描次数 n", 3:1:12, 8, value -> @sprintf("%.0f 次", value))
    temperature = add_slider!(controls, 2, "炉温 T", 150:2:200, 178, value -> @sprintf("%.0f ℃", value))
    temperature_u = add_slider!(controls, 3, "u(T)", 0.2:0.2:3.0, 1.0, value -> @sprintf("%.1f K", value))
    peak_noise = add_slider!(controls, 4, "峰位读数噪声", 0.00:0.01:0.20, 0.06, value -> @sprintf("%.2f V", value))
    contact_drift = add_slider!(controls, 5, "接触电势漂移", 0.00:0.01:0.20, 0.04, value -> @sprintf("%.2f V", value))
    calibration = add_slider!(controls, 6, "电压标定极限", 0.0:0.1:1.0, 0.4, value -> @sprintf("±%.1f%%", value))

    data = lift(repetitions.value, temperature.value, temperature_u.value, peak_noise.value, contact_drift.value, calibration.value) do count, temp, u_temp, noise, drift, cal
        uncertainty_model(Float64(count), Float64(temp), Float64(u_temp), Float64(noise), Float64(drift), Float64(cal))
    end

    scatterlines!(repeat_axis, lift(value -> value.repeat_indices, data), lift(value -> value.estimates, data), color = CYAN, markersize = 12, linewidth = 2.0)
    hlines!(repeat_axis, lift(value -> [value.mean_excitation], data), color = AMBER, linestyle = :dash, linewidth = 2.0, label = "均值")
    band!(repeat_axis, lift(value -> [0.5, 12.5], data), lift(value -> fill(value.mean_excitation - value.expanded, 2), data), lift(value -> fill(value.mean_excitation + value.expanded, 2), data), color = (GREEN, 0.18), label = "U=k=2 带")
    axislegend(repeat_axis, position = :rt, framevisible = false, labelsize = 9)
    barplot!(budget_axis, lift(value -> value.component_indices, data), lift(value -> value.components, data), color = [CYAN, PINK, AMBER, GREEN, VIOLET])

    values = (
        lift(value -> @sprintf("Ū₁ = %.4f V", value.mean_excitation), data),
        lift(value -> @sprintf("uᶜ = %.4f V", value.combined), data),
        lift(value -> @sprintf("U(k=2) = %.4f V", value.expanded), data),
        lift(value -> @sprintf("λ = %.2f ± %.2f nm", value.wavelength_nm, 2.0 * value.wavelength_uncertainty_nm), data),
    )
    detail = lift(data) do value
        @sprintf(
            "uᶜ²=uₐ²+u峰位²+u漂移²+uₜ²+u标定²；扩展不确定度取 k=2。波长用 u(λ)/λ=u(ΔU)/ΔU 传播。\n常量接触电势差被自由截距吸收，只有扫描间或扫描内漂移进入斜率不确定度；当前炉温引起的峰形宽化尺度 %.4f V。",
            value.thermal_broadening,
        )
    end
    add_metrics!(metrics, values, detail)
    bind_playback!(
        controls,
        7,
        repetitions,
        3:1:12,
        [(repetitions, 8), (temperature, 178), (temperature_u, 1.0), (peak_noise, 0.06), (contact_drift, 0.04), (calibration, 0.4)],
    )
    return figure
end

function run_self_test()
    apparatus = apparatus_model(28.0, 1.5, 1.2, 180.0, MERCURY_EXCITATION_EV)
    @assert apparatus.collision_count == 5
    @assert 0.0 <= apparatus.residual_energy < apparatus.excitation
    @assert isapprox(apparatus.wavelength_nm, 253.546418; rtol = 1.0e-6)
    @assert length(apparatus.collision_positions) == apparatus.collision_count
    apparatus_zero = apparatus_model(0.0, 3.0, 3.0, 150.0, 4.70)
    @assert apparatus_zero.collision_count == 0
    @assert isempty(apparatus_zero.collision_positions)
    @assert !apparatus_zero.collected

    curve = franck_hertz_curve(MERCURY_EXCITATION_EV, 1.2, 1.5, 178.0, 0.2)
    @assert length(curve.voltages) == 601
    @assert length(curve.derivative) == 600
    @assert length(curve.peak_positions) >= 8
    @assert all(isfinite, curve.currents)
    @assert isapprox(curve.mean_spacing, MERCURY_EXCITATION_EV; rtol = 1.0e-13)
    curve_extreme = franck_hertz_curve(5.10, 3.0, 3.0, 200.0, 1.0)
    @assert all(value -> value >= 0.0, curve_extreme.currents)

    exact = peak_analysis_model(MERCURY_EXCITATION_EV, 8.0, 1.2, 0.0, 0.0, 0.0)
    @assert isapprox(exact.fitted_excitation, MERCURY_EXCITATION_EV; rtol = 1.0e-13)
    @assert exact.fit.r_squared > 0.999999999
    @assert isapprox(exact.fit.intercept, 2.7; atol = 1.0e-12)
    noisy = peak_analysis_model(4.70, 4.0, 3.0, 1.0, 0.20, 0.10)
    @assert all(isfinite, noisy.measured_positions)
    @assert noisy.fitted_excitation > 0.0
    @assert noisy.wavelength_nm > 0.0

    budget = uncertainty_model(8.0, 178.0, 1.0, 0.06, 0.04, 0.4)
    @assert length(budget.estimates) == 8
    @assert budget.combined > 0.0
    @assert isapprox(budget.expanded, 2.0 * budget.combined; rtol = 1.0e-13)
    @assert budget.wavelength_uncertainty_nm > 0.0
    budget_zero = uncertainty_model(3.0, 178.0, 0.0, 0.0, 0.0, 0.0)
    @assert isfinite(budget_zero.combined)

    # 每个滑块都以端点值组合取样，确保可视化调参边界无 NaN/Inf。
    for ua in (0.0, 60.0), ur in (0.0, 3.0), uk in (0.0, 3.0), temp in (150.0, 200.0), u1 in (4.70, 5.10)
        value = apparatus_model(ua, ur, uk, temp, u1)
        @assert all(isfinite, value.energy_curve)
        @assert isfinite(value.wavelength_nm)
    end
    for u1 in (4.70, 5.10), uk in (0.0, 3.0), ur in (0.5, 3.0), temp in (150.0, 200.0), noise in (0.0, 1.0)
        value = franck_hertz_curve(u1, uk, ur, temp, noise)
        @assert all(isfinite, value.currents)
        @assert all(isfinite, value.derivative)
    end
    for u1 in (4.70, 5.10), count in (4.0, 10.0), uk in (0.0, 3.0), scale in (-1.0, 1.0), noise in (0.0, 0.20), curve in (-0.10, 0.10)
        value = peak_analysis_model(u1, count, uk, scale, noise, curve)
        @assert isfinite(value.fitted_excitation)
        @assert all(isfinite, value.adjacent_spacings)
    end
    for count in (3.0, 12.0), temp in (150.0, 200.0), u_temp in (0.2, 3.0), noise in (0.0, 0.20), drift in (0.0, 0.20), cal in (0.0, 1.0)
        value = uncertainty_model(count, temp, u_temp, noise, drift, cal)
        @assert all(isfinite, value.estimates)
        @assert isfinite(value.combined)
    end

    for builder in (apparatus_figure, curve_figure, analysis_figure, uncertainty_figure)
        @assert builder() isa Figure
    end
    @assert occursin(".franck-hertz-lab", PAGE_STYLE)
    @assert occursin("pointerdown", CLIENT_STATUS_SCRIPT)
    @assert occursin("baseWinscale * layoutScale", CLIENT_STATUS_SCRIPT)
    @assert occursin("franck-hertz-wgl-ready", CLIENT_STATUS_SCRIPT)
    @assert occursin("\\nWebGL 状态", CLIENT_STATUS_SCRIPT)
    @assert occursin("\\n页面地址", CLIENT_STATUS_SCRIPT)
    @assert occursin("\\n\" + event.filename", CLIENT_STATUS_SCRIPT)
    println("弗兰克-赫兹四个独立网页实验自检通过：管内机制、峰谷曲线、峰位拟合与不确定度均正常。")
end

const PAGE_STYLE = """
html, body { margin: 0; width: 100%; height: 100%; background: #0b0f14; color: #eef3f8; }
body { position: relative; overflow: hidden; font-family: 'Microsoft YaHei', 'Noto Sans CJK SC', sans-serif; }
.franck-hertz-lab { position: absolute; left: 0; top: 0; width: $(FIGURE_WIDTH)px; height: $(FIGURE_HEIGHT)px;
    margin: 0; padding: 0; box-sizing: border-box; overflow: hidden; background: #0b0f14;
    transform-origin: 0 0; }
.franck-hertz-diagnostic {
    position: fixed; left: 16px; right: 16px; bottom: 16px; z-index: 1002;
    display: none; padding: 10px 12px; color: #f7d7d7;
    background: rgba(64, 20, 28, .94); border: 1px solid rgba(255, 85, 105, .65);
    border-radius: 6px; font: 13px/1.5 ui-monospace, Consolas, monospace;
    white-space: pre-wrap;
}
.franck-hertz-diagnostic.visible { display: block; }
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
        if (!Number.isFinite(screen.__physicsBaseWinscale)) screen.__physicsBaseWinscale = screen.winscale;
        const baseWinscale = screen.__physicsBaseWinscale;
        screen.winscale = baseWinscale * layoutScale;
        window.clearTimeout(screen.__physicsPointerScaleTimer);
        screen.__physicsPointerScaleTimer = window.setTimeout(() => {
            if (canvas.wglmakie_screen === screen) screen.winscale = baseWinscale;
        }, 120);
    };
    const fitLayout = () => {
        const page = document.querySelector(".franck-hertz-lab");
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
    for (const eventName of ["mousemove", "mousedown", "mouseup", "pointerdown", "pointermove", "pointerup", "pointercancel", "wheel"]) {
        document.addEventListener(eventName, syncWGLPointerScale, { capture: true, passive: true });
    }

    const showDiagnostic = detail => {
        let box = document.getElementById("franck-hertz-diagnostic");
        if (!box) {
            box = document.createElement("div");
            box.id = "franck-hertz-diagnostic";
            box.className = "franck-hertz-diagnostic";
            document.body.appendChild(box);
        }
        box.textContent = detail;
        box.classList.add("visible");
        send("franck-hertz-wgl-failed", detail);
    };
    const webglProbe = () => {
        try {
            const canvas = document.createElement("canvas");
            if (canvas.getContext("webgl2", { antialias: true })) return "webgl2";
            if (canvas.getContext("webgl", { antialias: true }) || canvas.getContext("experimental-webgl")) return "webgl1";
        } catch (error) { return "error: " + error.message; }
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
            send("franck-hertz-wgl-ready", glStatus);
            return;
        }
        if (!ready && performance.now() - startedAt > 75000) {
            showDiagnostic("WGLMakie/Bonito 初始化超过 75 秒。\\nWebGL 状态：" + glStatus + "\\n页面地址：" + location.href);
            return;
        }
        window.setTimeout(check, 300);
    };
    window.addEventListener("error", event => showDiagnostic("浏览器脚本错误：" + event.message + "\\n" + event.filename + ":" + event.lineno));
    window.addEventListener("unhandledrejection", event => showDiagnostic("浏览器 Promise 错误：" + String(event.reason)));
    check();
})();
"""

function experiment_app(title, builder)
    return Bonito.App(; title = title) do
        figure = builder()
        DOM.div(
            DOM.style(PAGE_STYLE),
            DOM.div(figure; class = "franck-hertz-lab"),
            DOM.script(CLIENT_STATUS_SCRIPT),
        )
    end
end

function index_app()
    links = [
        DOM.a(name; href = path, style = "color:#73d7cf;margin-right:24px")
        for (name, path) in (
            ("管内电场与非弹性碰撞", "./apparatus"),
            ("收集电流峰谷曲线", "./curve"),
            ("峰位拟合与激发电势", "./analysis"),
            ("重复测量与不确定度", "./uncertainty"),
        )
    ]
    return Bonito.App(
        DOM.div(
            DOM.style(PAGE_STYLE),
            DOM.h1("弗兰克-赫兹实验"),
            DOM.div(links...),
            DOM.p(SAFETY_TEXT;
                style = "margin-top:24px;color:#f0b4b4;max-width:900px;line-height:1.7"),
            style = "padding:32px;background:#0b0f14;color:#eef3f8;min-height:100vh",
        );
        title = "弗兰克-赫兹实验",
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
    host = get(ENV, "FRANCK_HERTZ_WEB_HOST", "127.0.0.1")
    port = parse(Int, get(ENV, "FRANCK_HERTZ_WEB_PORT", "9394"))
    proxy_url = strip(get(ENV, "FRANCK_HERTZ_WEB_PROXY_URL", "."))
    isempty(proxy_url) && (proxy_url = ".")
    server = Bonito.Server(host, port; proxy_url = proxy_url)
    Bonito.route!(server, "/__physics_health__" => health_app())
    Bonito.route!(server, "/" => index_app())
    Bonito.route!(server, "/apparatus" => experiment_app("管内电场与非弹性碰撞", apparatus_figure))
    Bonito.route!(server, "/curve" => experiment_app("收集电流峰谷曲线", curve_figure))
    Bonito.route!(server, "/analysis" => experiment_app("峰位拟合与激发电势", analysis_figure))
    Bonito.route!(server, "/uncertainty" => experiment_app("重复测量与不确定度", uncertainty_figure))
    println("弗兰克-赫兹网页实验已启动：http://$(host):$(port)")
    wait(server)
end

if abspath(PROGRAM_FILE) == @__FILE__
    main()
end
