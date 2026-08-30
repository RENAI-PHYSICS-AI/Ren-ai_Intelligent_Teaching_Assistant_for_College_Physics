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

const WATER_SPECIFIC_HEAT = 4180.0
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
const CJK_PROBE_TEXT = "固体比热容混合法量热器水当量冷却修正电加热拟合不确定度"
const HEALTH_MARKER = "physics-experiment:specific-heat"
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
    rowsize!(grid, 1, 28)
    rowsize!(grid, 2, 66)
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

function validate_mixing_inputs(mass_s, mass_w, water_equivalent, solid_initial, water_initial, specific_heat)
    Float64(mass_s) > 0 || throw(ArgumentError("固体质量必须大于零"))
    Float64(mass_w) > 0 || throw(ArgumentError("水的质量必须大于零"))
    Float64(water_equivalent) >= 0 || throw(ArgumentError("量热器水当量不能为负"))
    Float64(solid_initial) > Float64(water_initial) || throw(ArgumentError("固体初温必须高于水的初温"))
    Float64(specific_heat) > 0 || throw(ArgumentError("比热容必须大于零"))
    return nothing
end

function mixing_equilibrium(
    mass_s,
    mass_w,
    water_equivalent,
    solid_initial,
    water_initial,
    specific_heat;
    water_specific_heat = WATER_SPECIFIC_HEAT,
)
    validate_mixing_inputs(
        mass_s,
        mass_w,
        water_equivalent,
        solid_initial,
        water_initial,
        specific_heat,
    )
    solid_capacity = Float64(mass_s) * Float64(specific_heat)
    receiver_capacity = (Float64(mass_w) + Float64(water_equivalent)) * Float64(water_specific_heat)
    return (
        solid_capacity * Float64(solid_initial) + receiver_capacity * Float64(water_initial)
    ) / (solid_capacity + receiver_capacity)
end

function mixing_specific_heat(
    mass_s,
    mass_w,
    water_equivalent,
    solid_initial,
    water_initial,
    equilibrium;
    water_specific_heat = WATER_SPECIFIC_HEAT,
)
    hot_drop = Float64(solid_initial) - Float64(equilibrium)
    receiver_rise = Float64(equilibrium) - Float64(water_initial)
    Float64(mass_s) > 0 || throw(ArgumentError("固体质量必须大于零"))
    Float64(mass_w) > 0 || throw(ArgumentError("水的质量必须大于零"))
    Float64(water_equivalent) >= 0 || throw(ArgumentError("量热器水当量不能为负"))
    hot_drop > 0 || throw(ArgumentError("平衡温度必须低于固体初温"))
    receiver_rise > 0 || throw(ArgumentError("平衡温度必须高于水初温"))
    return (
        (Float64(mass_w) + Float64(water_equivalent)) * Float64(water_specific_heat) * receiver_rise
    ) / (Float64(mass_s) * hot_drop)
end

function calorimeter_water_equivalent(mass_hot, mass_cold, hot_initial, cold_initial, equilibrium)
    hot_drop = Float64(hot_initial) - Float64(equilibrium)
    cold_rise = Float64(equilibrium) - Float64(cold_initial)
    Float64(mass_hot) > 0 || throw(ArgumentError("热水质量必须大于零"))
    Float64(mass_cold) > 0 || throw(ArgumentError("冷水质量必须大于零"))
    hot_drop > 0 && cold_rise > 0 || throw(ArgumentError("混合温度必须位于冷热水初温之间"))
    return Float64(mass_hot) * hot_drop / cold_rise - Float64(mass_cold)
end

function mixing_model(
    mass_s_g,
    mass_w_g,
    water_equivalent_g,
    solid_initial,
    water_initial,
    specific_heat,
)
    mass_s = Float64(mass_s_g) * 1.0e-3
    mass_w = Float64(mass_w_g) * 1.0e-3
    water_equivalent = Float64(water_equivalent_g) * 1.0e-3
    equilibrium = mixing_equilibrium(
        mass_s,
        mass_w,
        water_equivalent,
        solid_initial,
        water_initial,
        specific_heat,
    )
    inferred = mixing_specific_heat(
        mass_s,
        mass_w,
        water_equivalent,
        solid_initial,
        water_initial,
        equilibrium,
    )
    solid_capacity = mass_s * Float64(specific_heat)
    receiver_capacity = (mass_w + water_equivalent) * WATER_SPECIFIC_HEAT
    heat = solid_capacity * (Float64(solid_initial) - equilibrium)
    times = collect(range(0.0, 180.0; length = 181))
    relaxation = exp.(-times ./ 36.0)
    solid_temperatures = equilibrium .+ (Float64(solid_initial) - equilibrium) .* relaxation
    receiver_temperatures = equilibrium .+ (Float64(water_initial) - equilibrium) .* relaxation
    capacity_values = collect(range(180.0, 1050.0; length = 180))
    equilibrium_values = [
        mixing_equilibrium(
            mass_s,
            mass_w,
            water_equivalent,
            solid_initial,
            water_initial,
            value,
        )
        for value in capacity_values
    ]
    no_calorimeter = mixing_specific_heat(
        mass_s,
        mass_w,
        0.0,
        solid_initial,
        water_initial,
        equilibrium,
    )
    return (;
        mass_s,
        mass_w,
        water_equivalent,
        specific_heat = Float64(specific_heat),
        equilibrium,
        inferred,
        solid_capacity,
        receiver_capacity,
        heat,
        times,
        solid_temperatures,
        receiver_temperatures,
        capacity_values,
        equilibrium_values,
        no_calorimeter,
        neglect_bias_percent = 100.0 * (no_calorimeter - Float64(specific_heat)) / Float64(specific_heat),
        balance_error = heat - receiver_capacity * (equilibrium - Float64(water_initial)),
    )
end

function mixing_figure()
    figure, controls, metrics = base_figure()
    temperature_axis = Axis(
        figure[1, 1],
        title = "绝热混合的热平衡",
        xlabel = "混合后时间 t / s",
        ylabel = "温度 T / ℃",
    )
    sensitivity_axis = Axis(
        figure[1, 2],
        title = "平衡温度对固体比热的灵敏度",
        xlabel = "固体比热 c / J·kg⁻¹·K⁻¹",
        ylabel = "绝热平衡温度 Tₑ / ℃",
    )

    mass_s = add_slider!(controls, 1, "固体质量 mₛ", 60:5:250, 120, value -> @sprintf("%.0f g", value))
    mass_w = add_slider!(controls, 2, "水的质量 mₓ", 100:10:350, 200, value -> @sprintf("%.0f g", value))
    equivalent = add_slider!(controls, 3, "量热器水当量 W", 0:2:60, 25, value -> @sprintf("%.0f g", value))
    solid_initial = add_slider!(controls, 4, "固体初温 Tₛ", 60:2:100, 90, value -> @sprintf("%.0f ℃", value))
    water_initial = add_slider!(controls, 5, "水的初温 Tₓ", 15:1:30, 22, value -> @sprintf("%.0f ℃", value))
    specific_heat = add_slider!(controls, 6, "固体比热 c", 200:5:1000, 385, value -> @sprintf("%.0f J/(kg·K)", value))

    data = lift(
        mass_s.value,
        mass_w.value,
        equivalent.value,
        solid_initial.value,
        water_initial.value,
        specific_heat.value,
    ) do ms, mw, water_eq, ts, tw, cp
        mixing_model(Float64(ms), Float64(mw), Float64(water_eq), Float64(ts), Float64(tw), Float64(cp))
    end

    lines!(temperature_axis, lift(value -> value.times, data), lift(value -> value.solid_temperatures, data), color = PINK, linewidth = 2.8, label = "固体")
    lines!(temperature_axis, lift(value -> value.times, data), lift(value -> value.receiver_temperatures, data), color = CYAN, linewidth = 2.8, label = "水+量热器")
    hlines!(temperature_axis, lift(value -> [value.equilibrium], data), color = AMBER, linestyle = :dash, linewidth = 2.0, label = "Tₑ")
    axislegend(temperature_axis, position = :rc, framevisible = false, labelsize = 10)

    lines!(sensitivity_axis, lift(value -> value.capacity_values, data), lift(value -> value.equilibrium_values, data), color = GREEN, linewidth = 2.8)
    scatter!(sensitivity_axis, lift(value -> [value.specific_heat], data), lift(value -> [value.equilibrium], data), color = AMBER, markersize = 16)

    values = (
        lift(value -> @sprintf("Tₑ = %.3f ℃", value.equilibrium), data),
        lift(value -> @sprintf("Q = %.2f J", value.heat), data),
        lift(value -> @sprintf("c测 = %.2f J/(kg·K)", value.inferred), data),
        lift(value -> @sprintf("忽略 W 偏差 = %+.2f%%", value.neglect_bias_percent), data),
    )
    detail = lift(data) do value
        @sprintf(
            "热平衡：mₛc(Tₛ-Tₑ)=(mₓ+W)cₓ(Tₑ-Tₓ)，因而 c=(mₓ+W)cₓ(Tₑ-Tₓ)/[mₛ(Tₛ-Tₑ)]。\n水当量可用冷热水标定：W=mₕ(Tₕ-Tₑ)/(Tₑ-Tₒ)-mₒ。当前能量闭合残差 %.3e J。",
            value.balance_error,
        )
    end
    add_metrics!(metrics, values, detail)
    bind_playback!(
        controls,
        7,
        solid_initial,
        60:2:100,
        [(mass_s, 120), (mass_w, 200), (equivalent, 25), (solid_initial, 90), (water_initial, 22), (specific_heat, 385)],
    )
    return figure
end

function cooling_model(loss_rate_min, first_delay_s, interval_s, thermometer_noise, ambient_temperature)
    mass_s = 0.120
    mass_w = 0.200
    water_equivalent = 0.025
    solid_initial = 90.0
    water_initial = 22.0
    true_specific_heat = 385.0
    adiabatic_equilibrium = mixing_equilibrium(
        mass_s,
        mass_w,
        water_equivalent,
        solid_initial,
        water_initial,
        true_specific_heat,
    )
    ambient = Float64(ambient_temperature)
    ambient < water_initial || throw(ArgumentError("环境温度应低于量热器初温"))
    rate = Float64(loss_rate_min) / 60.0
    rate > 0 || throw(ArgumentError("冷却常数必须大于零"))
    first_delay = Float64(first_delay_s)
    interval = Float64(interval_s)
    first_delay >= 0 || throw(ArgumentError("首次读数延迟不能为负"))
    interval > 0 || throw(ArgumentError("采样间隔必须大于零"))
    sample_times = first_delay .+ interval .* collect(0:5)
    noise_pattern = [0.00, 0.62, -0.44, 0.31, -0.55, 0.18]
    ideal_samples = ambient .+ (adiabatic_equilibrium - ambient) .* exp.(-rate .* sample_times)
    observed_samples = ideal_samples .+ Float64(thermometer_noise) .* noise_pattern
    all(observed_samples .> ambient) || throw(ArgumentError("温度噪声使观测值不再高于环境温度"))
    log_excess = log.(observed_samples .- ambient)
    fit = linear_fit(sample_times, log_excess)
    corrected_equilibrium = ambient + exp(fit.intercept)
    corrected_specific_heat = mixing_specific_heat(
        mass_s,
        mass_w,
        water_equivalent,
        solid_initial,
        water_initial,
        corrected_equilibrium,
    )
    naive_specific_heat = mixing_specific_heat(
        mass_s,
        mass_w,
        water_equivalent,
        solid_initial,
        water_initial,
        observed_samples[1],
    )
    curve_times = collect(range(0.0, maximum(sample_times) + interval; length = 240))
    curve_temperatures = ambient .+ (adiabatic_equilibrium - ambient) .* exp.(-rate .* curve_times)
    fitted_temperatures = ambient .+ exp.(fit.intercept .+ fit.slope .* curve_times)
    return (;
        mass_s,
        mass_w,
        water_equivalent,
        solid_initial,
        water_initial,
        true_specific_heat,
        adiabatic_equilibrium,
        ambient,
        rate,
        sample_times,
        ideal_samples,
        observed_samples,
        log_excess,
        fit,
        corrected_equilibrium,
        corrected_specific_heat,
        naive_specific_heat,
        curve_times,
        curve_temperatures,
        fitted_temperatures,
        corrected_error_percent = 100.0 * (corrected_specific_heat - true_specific_heat) / true_specific_heat,
        naive_error_percent = 100.0 * (naive_specific_heat - true_specific_heat) / true_specific_heat,
    )
end

function cooling_figure()
    figure, controls, metrics = base_figure()
    cooling_axis = Axis(
        figure[1, 1],
        title = "牛顿冷却曲线与混合时刻外推",
        xlabel = "混合后时间 t / s",
        ylabel = "温度 T / ℃",
    )
    linear_axis = Axis(
        figure[1, 2],
        title = "ln(T-Tₐ) 线性检验",
        xlabel = "时间 t / s",
        ylabel = "ln[(T-Tₐ)/K]",
    )

    loss_rate = add_slider!(controls, 1, "冷却常数 k", 0.02:0.01:0.20, 0.08, value -> @sprintf("%.2f min⁻¹", value))
    delay = add_slider!(controls, 2, "首次读数延迟", 0:10:180, 60, value -> @sprintf("%.0f s", value))
    interval = add_slider!(controls, 3, "采样间隔", 15:5:60, 30, value -> @sprintf("%.0f s", value))
    noise = add_slider!(controls, 4, "温度读数散布", 0.00:0.01:0.12, 0.03, value -> @sprintf("±%.2f K", value))
    # 保证在滑块的极端组合下，首次读数仍高于量热器初温，
    # 从而“未修正的混合法结果”仍有物理意义。
    ambient = add_slider!(controls, 5, "环境温度 Tₐ", 19:0.5:21, 19, value -> @sprintf("%.1f ℃", value))

    data = lift(loss_rate.value, delay.value, interval.value, noise.value, ambient.value) do k, t0, dt, scatter, ta
        cooling_model(Float64(k), Float64(t0), Float64(dt), Float64(scatter), Float64(ta))
    end

    lines!(cooling_axis, lift(value -> value.curve_times, data), lift(value -> value.curve_temperatures, data), color = CYAN, linewidth = 2.8, label = "理想冷却曲线")
    lines!(cooling_axis, lift(value -> value.curve_times, data), lift(value -> value.fitted_temperatures, data), color = GREEN, linestyle = :dash, linewidth = 2.2, label = "实测拟合")
    scatter!(cooling_axis, lift(value -> value.sample_times, data), lift(value -> value.observed_samples, data), color = PINK, markersize = 12, label = "温度读数")
    scatter!(cooling_axis, [0.0], lift(value -> [value.corrected_equilibrium], data), color = AMBER, marker = :diamond, markersize = 17, label = "外推 Tₑ")
    axislegend(cooling_axis, position = :rt, framevisible = false, labelsize = 9)

    scatter!(linear_axis, lift(value -> value.sample_times, data), lift(value -> value.log_excess, data), color = PINK, markersize = 12, label = "观测")
    lines!(linear_axis, lift(value -> value.sample_times, data), lift(value -> value.fit.predicted, data), color = GREEN, linewidth = 2.8, label = "线性拟合")
    axislegend(linear_axis, position = :rt, framevisible = false, labelsize = 10)

    values = (
        lift(value -> @sprintf("Tₑ,修正 = %.3f ℃", value.corrected_equilibrium), data),
        lift(value -> @sprintf("c修正 = %.1f J/(kg·K)", value.corrected_specific_heat), data),
        lift(value -> @sprintf("c首读 = %.1f J/(kg·K)", value.naive_specific_heat), data),
        lift(value -> @sprintf("R² = %.5f", value.fit.r_squared), data),
    )
    detail = lift(data) do value
        @sprintf(
            "牛顿冷却：T-Tₐ=(Tₑ-Tₐ)e⁻ᵏᵗ；对 ln(T-Tₐ) 对 t 线性拟合，截距外推到混合时刻 t=0。\n当前首读法偏差 %+.2f%%，外推修正后偏差 %+.2f%%；该修正依赖冷却常数在拟合区间近似不变。",
            value.naive_error_percent,
            value.corrected_error_percent,
        )
    end
    add_metrics!(metrics, values, detail)
    bind_playback!(
        controls,
        6,
        delay,
        0:10:180,
        [(loss_rate, 0.08), (delay, 60), (interval, 30), (noise, 0.03), (ambient, 19)],
    )
    return figure
end

function electrical_model(mass_g, specific_heat, voltage, current, loss_conductance, duration_s; ambient = 20.0)
    mass = Float64(mass_g) * 1.0e-3
    capacity = Float64(specific_heat)
    power = Float64(voltage) * Float64(current)
    conductance = Float64(loss_conductance)
    duration = Float64(duration_s)
    mass > 0 || throw(ArgumentError("固体质量必须大于零"))
    capacity > 0 || throw(ArgumentError("比热容必须大于零"))
    power > 0 || throw(ArgumentError("电加热功率必须大于零"))
    conductance >= 0 || throw(ArgumentError("散热系数不能为负"))
    duration > 0 || throw(ArgumentError("加热时间必须大于零"))
    heat_capacity = mass * capacity
    times = collect(range(0.0, duration; length = 241))
    temperature_rise = if conductance == 0.0
        power .* times ./ heat_capacity
    else
        power / conductance .* (1.0 .- exp.(-conductance .* times ./ heat_capacity))
    end
    temperatures = Float64(ambient) .+ temperature_rise
    input_energy = power .* times
    stored_energy = heat_capacity .* temperature_rise
    lost_energy = input_energy .- stored_energy
    final_rise = temperature_rise[end]
    final_rise > 0 || throw(ArgumentError("最终温升必须大于零"))
    naive_specific_heat = input_energy[end] / (mass * final_rise)
    corrected_specific_heat = (input_energy[end] - lost_energy[end]) / (mass * final_rise)
    return (;
        mass,
        specific_heat = capacity,
        voltage = Float64(voltage),
        current = Float64(current),
        power,
        conductance,
        duration,
        heat_capacity,
        times,
        temperatures,
        temperature_rise,
        input_energy,
        stored_energy,
        lost_energy,
        final_rise,
        naive_specific_heat,
        corrected_specific_heat,
        lost_fraction = lost_energy[end] / input_energy[end],
        energy_balance_error = input_energy[end] - stored_energy[end] - lost_energy[end],
    )
end

function electrical_figure()
    figure, controls, metrics = base_figure()
    temperature_axis = Axis(
        figure[1, 1],
        title = "恒功率电加热与散热",
        xlabel = "加热时间 t / s",
        ylabel = "样品温度 T / ℃",
    )
    energy_axis = Axis(
        figure[1, 2],
        title = "能量分解",
        xlabel = "加热时间 t / s",
        ylabel = "能量 Q / kJ",
    )

    mass = add_slider!(controls, 1, "固体质量 m", 200:20:800, 500, value -> @sprintf("%.0f g", value))
    specific_heat = add_slider!(controls, 2, "真实比热 c", 200:5:1000, 385, value -> @sprintf("%.0f J/(kg·K)", value))
    voltage = add_slider!(controls, 3, "电压 U", 4:1:20, 12, value -> @sprintf("%.0f V", value))
    current = add_slider!(controls, 4, "电流 I", 0.5:0.1:3.0, 2.0, value -> @sprintf("%.1f A", value))
    loss = add_slider!(controls, 5, "散热系数 H", 0.00:0.02:0.50, 0.20, value -> @sprintf("%.2f W/K", value))
    duration = add_slider!(controls, 6, "加热时间", 120:30:900, 600, value -> @sprintf("%.0f s", value))

    data = lift(mass.value, specific_heat.value, voltage.value, current.value, loss.value, duration.value) do m, cp, u, i, h, t
        electrical_model(Float64(m), Float64(cp), Float64(u), Float64(i), Float64(h), Float64(t))
    end

    lines!(temperature_axis, lift(value -> value.times, data), lift(value -> value.temperatures, data), color = PINK, linewidth = 2.8, label = "考虑散热")
    lines!(temperature_axis, lift(value -> value.times, data), lift(value -> 20.0 .+ value.power .* value.times ./ value.heat_capacity, data), color = CYAN, linestyle = :dash, linewidth = 2.2, label = "绝热近似")
    axislegend(temperature_axis, position = :lt, framevisible = false, labelsize = 10)

    lines!(energy_axis, lift(value -> value.times, data), lift(value -> value.input_energy ./ 1000.0, data), color = AMBER, linewidth = 2.8, label = "UIt")
    lines!(energy_axis, lift(value -> value.times, data), lift(value -> value.stored_energy ./ 1000.0, data), color = GREEN, linewidth = 2.8, label = "mcΔT")
    lines!(energy_axis, lift(value -> value.times, data), lift(value -> value.lost_energy ./ 1000.0, data), color = VIOLET, linewidth = 2.4, label = "散热损失")
    axislegend(energy_axis, position = :lt, framevisible = false, labelsize = 10)

    values = (
        lift(value -> @sprintf("P = %.2f W", value.power), data),
        lift(value -> @sprintf("ΔT = %.2f K", value.final_rise), data),
        lift(value -> @sprintf("c绝热 = %.1f J/(kg·K)", value.naive_specific_heat), data),
        lift(value -> @sprintf("散热份额 = %.1f%%", 100.0 * value.lost_fraction), data),
    )
    detail = lift(data) do value
        @sprintf(
            "集总热容模型：mc dT/dt=UI-H(T-Tₐ)；已知 H 时，mcΔT=UIt-∫H(T-Tₐ)dt。\n忽略散热得 c=%.1f，能量修正得 c=%.1f J/(kg·K)；能量闭合残差 %.3e J。",
            value.naive_specific_heat,
            value.corrected_specific_heat,
            value.energy_balance_error,
        )
    end
    add_metrics!(metrics, values, detail)
    bind_playback!(
        controls,
        7,
        duration,
        120:30:900,
        [(mass, 500), (specific_heat, 385), (voltage, 12), (current, 2.0), (loss, 0.20), (duration, 600)],
    )
    return figure
end

const MATERIALS = (
    (; name = "铜", specific_heat = 385.0),
    (; name = "铝", specific_heat = 897.0),
    (; name = "铁", specific_heat = 449.0),
)

function fit_model(material_index, repetitions, temperature_uncertainty, mass_uncertainty_g, power_relative_percent, loss_relative_percent)
    index = clamp(round(Int, material_index), 1, length(MATERIALS))
    material = MATERIALS[index]
    count = clamp(round(Int, repetitions), 4, 10)
    u_temperature = Float64(temperature_uncertainty)
    u_mass = Float64(mass_uncertainty_g) * 1.0e-3
    u_power = Float64(power_relative_percent) / 100.0
    u_loss = Float64(loss_relative_percent) / 100.0
    all(value -> value >= 0, (u_temperature, u_mass, u_power, u_loss)) ||
        throw(ArgumentError("标准不确定度不能为负"))
    mass_pattern = [-0.72, 0.35, -0.18, 0.61, -0.47, 0.26, -0.09, 0.43, -0.31, 0.14]
    temperature_pattern = [0.00, 0.62, -0.44, 0.31, -0.55, 0.18, 0.47, -0.26, 0.12, -0.38]
    energy_pattern = [0.41, -0.53, 0.24, -0.17, 0.58, -0.32, 0.09, 0.36, -0.46, 0.20]
    loss_pattern = [-0.30, 0.45, -0.19, 0.52, -0.41, 0.16, 0.28, -0.37, 0.11, -0.22]
    masses_true = [0.180 + 0.020 * (i - 1) for i in 1:count]
    rises_true = [7.0 + 1.8 * (i - 1) for i in 1:count]
    x_true = masses_true .* rises_true
    net_energy_true = material.specific_heat .* x_true
    masses_measured = masses_true .+ u_mass .* mass_pattern[1:count]
    rises_measured = rises_true .+ u_temperature .* temperature_pattern[1:count]
    x_measured = masses_measured .* rises_measured
    relative_energy_perturbation = u_power .* energy_pattern[1:count] .+ u_loss .* loss_pattern[1:count]
    net_energy_measured = net_energy_true .* (1.0 .+ relative_energy_perturbation)
    fit = linear_fit(x_measured, net_energy_measured)
    fitted_specific_heat = fit.slope
    regression_relative = abs(fit.slope_uncertainty / fit.slope)
    temperature_relative = u_temperature / (sum(rises_true) / count)
    mass_relative = u_mass / (sum(masses_true) / count)
    component_labels = ["拟合", "温差", "质量", "电功率", "热损"]
    component_relative = [
        regression_relative,
        temperature_relative,
        mass_relative,
        u_power,
        u_loss,
    ]
    combined_relative = sqrt(sum(abs2, component_relative))
    residual_rms = sqrt(sum(abs2, fit.residuals) / count)
    residual_max_abs = maximum(abs, fit.residuals)
    return (;
        material,
        count,
        masses_true,
        rises_true,
        x_true,
        net_energy_true,
        masses_measured,
        rises_measured,
        x_measured,
        net_energy_measured,
        fit,
        fitted_specific_heat,
        component_labels,
        component_indices = collect(1:length(component_labels)),
        component_relative,
        component_percent = 100.0 .* component_relative,
        combined_relative,
        specific_heat_uncertainty = fitted_specific_heat * combined_relative,
        residual_rms,
        residual_max_abs,
        relative_error_percent = 100.0 * (fitted_specific_heat - material.specific_heat) / material.specific_heat,
    )
end

function fit_figure()
    figure, controls, metrics = base_figure()
    fit_axis = Axis(
        figure[1, 1],
        title = "多次测量：净输入热量拟合",
        xlabel = "mΔT / kg·K",
        ylabel = "Q净 / J",
    )
    budget_axis = Axis(
        figure[1, 2],
        title = "比热容相对标准不确定度分量",
        xlabel = "来源",
        ylabel = "相对分量 / %",
        xticks = (collect(1:5), ["拟合", "ΔT", "m", "UI", "Q损"]),
    )

    material = add_slider!(controls, 1, "材料（1铜/2铝/3铁）", 1:1:3, 1, value -> MATERIALS[round(Int, value)].name)
    repetitions = add_slider!(controls, 2, "测量次数 n", 4:1:10, 8, value -> @sprintf("%.0f 次", value))
    temperature_u = add_slider!(controls, 3, "u(ΔT)", 0.00:0.01:0.20, 0.05, value -> @sprintf("%.2f K", value))
    mass_u = add_slider!(controls, 4, "u(m)", 0.00:0.02:0.20, 0.10, value -> @sprintf("%.2f g", value))
    power_u = add_slider!(controls, 5, "uᵣ(UI)", 0.0:0.1:1.0, 0.4, value -> @sprintf("%.1f%%", value))
    loss_u = add_slider!(controls, 6, "uᵣ(Q损)", 0.0:0.1:1.0, 0.3, value -> @sprintf("%.1f%%", value))

    data = lift(material.value, repetitions.value, temperature_u.value, mass_u.value, power_u.value, loss_u.value) do selected, count, u_t, u_m, u_p, u_l
        fit_model(Float64(selected), Float64(count), Float64(u_t), Float64(u_m), Float64(u_p), Float64(u_l))
    end

    scatter!(fit_axis, lift(value -> value.x_measured, data), lift(value -> value.net_energy_measured, data), color = CYAN, markersize = 13, label = "测量值")
    lines!(fit_axis, lift(value -> value.x_measured, data), lift(value -> value.fit.predicted, data), color = GREEN, linewidth = 2.8, label = "Q=c(mΔT)+b")
    axislegend(fit_axis, position = :lt, framevisible = false, labelsize = 10)

    barplot!(budget_axis, lift(value -> value.component_indices, data), lift(value -> value.component_percent, data), color = [CYAN, PINK, AMBER, GREEN, VIOLET])

    values = (
        lift(value -> @sprintf("材料：%s", value.material.name), data),
        lift(value -> @sprintf("c = %.1f ± %.1f J/(kg·K)", value.fitted_specific_heat, value.specific_heat_uncertainty), data),
        lift(value -> @sprintf("R² = %.6f", value.fit.r_squared), data),
        lift(value -> @sprintf("残差 RMS/max = %.2f/%.2f J", value.residual_rms, value.residual_max_abs), data),
    )
    detail = lift(data) do value
        @sprintf(
            "对每次经散热修正的 Q净 与 mΔT 作自由截距线性拟合，斜率为 c；截距=%+.2f J，相对偏差 %+.2f%%。\n合成相对标准不确定度 %.3f%%（k=1）；同时检查残差而非只看 R²，以识别温度依赖散热等模型失配。",
            value.fit.intercept,
            value.relative_error_percent,
            100.0 * value.combined_relative,
        )
    end
    add_metrics!(metrics, values, detail)
    bind_playback!(
        controls,
        7,
        repetitions,
        4:1:10,
        [(material, 1), (repetitions, 8), (temperature_u, 0.05), (mass_u, 0.10), (power_u, 0.4), (loss_u, 0.3)],
    )
    return figure
end

function run_self_test()
    water_equivalent = calorimeter_water_equivalent(0.100, 0.100, 60.0, 20.0, 38.0)
    @assert water_equivalent > 0.0
    calibration_temperature = (
        0.100 * 60.0 + (0.100 + water_equivalent) * 20.0
    ) / (0.100 + 0.100 + water_equivalent)
    @assert isapprox(calibration_temperature, 38.0; atol = 1.0e-12)

    mixing = mixing_model(120.0, 200.0, 25.0, 90.0, 22.0, 385.0)
    @assert 22.0 < mixing.equilibrium < 90.0
    @assert isapprox(mixing.inferred, 385.0; rtol = 1.0e-13)
    @assert abs(mixing.balance_error) < 1.0e-11
    @assert mixing.no_calorimeter < mixing.specific_heat

    cooling_exact = cooling_model(0.08, 60.0, 30.0, 0.0, 19.0)
    @assert cooling_exact.fit.slope < 0.0
    @assert cooling_exact.fit.r_squared > 0.999999999
    @assert isapprox(cooling_exact.corrected_equilibrium, cooling_exact.adiabatic_equilibrium; rtol = 1.0e-12)
    @assert isapprox(cooling_exact.corrected_specific_heat, cooling_exact.true_specific_heat; rtol = 1.0e-11)
    @assert cooling_exact.naive_specific_heat < cooling_exact.true_specific_heat
    cooling_extreme = cooling_model(0.20, 180.0, 60.0, 0.12, 19.0)
    @assert all(cooling_extreme.observed_samples .> cooling_extreme.ambient)
    @assert cooling_extreme.observed_samples[1] > cooling_extreme.water_initial
    @assert cooling_extreme.corrected_specific_heat > 0.0

    electrical_adiabatic = electrical_model(500.0, 385.0, 12.0, 2.0, 0.0, 600.0)
    @assert isapprox(electrical_adiabatic.final_rise, electrical_adiabatic.power * electrical_adiabatic.duration / electrical_adiabatic.heat_capacity; rtol = 1.0e-13)
    @assert electrical_adiabatic.lost_fraction == 0.0
    @assert isapprox(electrical_adiabatic.naive_specific_heat, 385.0; rtol = 1.0e-13)
    electrical_lossy = electrical_model(500.0, 385.0, 12.0, 2.0, 0.2, 600.0)
    @assert electrical_lossy.lost_fraction > 0.0
    @assert electrical_lossy.naive_specific_heat > electrical_lossy.specific_heat
    @assert isapprox(electrical_lossy.corrected_specific_heat, electrical_lossy.specific_heat; rtol = 1.0e-13)
    @assert abs(electrical_lossy.energy_balance_error) < 1.0e-11

    fitted_exact = fit_model(1.0, 8.0, 0.0, 0.0, 0.0, 0.0)
    @assert fitted_exact.material.name == "铜"
    @assert fitted_exact.fit.r_squared > 0.999999999
    @assert abs(fitted_exact.fit.intercept) < 1.0e-10
    @assert isapprox(fitted_exact.fitted_specific_heat, 385.0; rtol = 1.0e-12)
    fitted_noisy = fit_model(2.0, 8.0, 0.05, 0.10, 0.4, 0.3)
    @assert fitted_noisy.material.name == "铝"
    @assert fitted_noisy.combined_relative > 0.0
    @assert fitted_noisy.specific_heat_uncertainty > 0.0
    @assert fitted_noisy.residual_rms > 0.0

    for builder in (mixing_figure, cooling_figure, electrical_figure, fit_figure)
        @assert builder() isa Figure
    end
    @assert occursin(".specific-heat-lab", PAGE_STYLE)
    @assert occursin("pointerdown", CLIENT_STATUS_SCRIPT)
    @assert occursin("baseWinscale * layoutScale", CLIENT_STATUS_SCRIPT)
    @assert occursin("specific-heat-wgl-ready", CLIENT_STATUS_SCRIPT)
    @assert occursin("\\nWebGL 状态", CLIENT_STATUS_SCRIPT)
    @assert occursin("\\n页面地址", CLIENT_STATUS_SCRIPT)
    @assert occursin("\\n\" + event.filename", CLIENT_STATUS_SCRIPT)
    println("固体比热容四个独立网页实验自检通过：混合热平衡、冷却外推、电加热及多次拟合均正常。")
end

const PAGE_STYLE = """
html, body { margin: 0; width: 100%; height: 100%; background: #0b0f14; color: #eef3f8; }
body { position: relative; overflow: hidden; font-family: 'Microsoft YaHei', 'Noto Sans CJK SC', sans-serif; }
.specific-heat-lab { position: absolute; left: 0; top: 0; width: $(FIGURE_WIDTH)px; height: $(FIGURE_HEIGHT)px;
    margin: 0; padding: 0; box-sizing: border-box; overflow: hidden; background: #0b0f14;
    transform-origin: 0 0; }
.specific-heat-diagnostic {
    position: fixed; left: 16px; right: 16px; bottom: 16px; z-index: 1002;
    display: none; padding: 10px 12px; color: #f7d7d7;
    background: rgba(64, 20, 28, .94); border: 1px solid rgba(255, 85, 105, .65);
    border-radius: 6px; font: 13px/1.5 ui-monospace, Consolas, monospace;
    white-space: pre-wrap;
}
.specific-heat-diagnostic.visible { display: block; }
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
        const page = document.querySelector(".specific-heat-lab");
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
        let box = document.getElementById("specific-heat-diagnostic");
        if (!box) {
            box = document.createElement("div");
            box.id = "specific-heat-diagnostic";
            box.className = "specific-heat-diagnostic";
            document.body.appendChild(box);
        }
        box.textContent = detail;
        box.classList.add("visible");
        send("specific-heat-wgl-failed", detail);
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
            send("specific-heat-wgl-ready", glStatus);
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
            DOM.div(figure; class = "specific-heat-lab"),
            DOM.script(CLIENT_STATUS_SCRIPT),
        )
    end
end

function index_app()
    links = [
        DOM.a(name; href = path, style = "color:#73d7cf;margin-right:24px")
        for (name, path) in (
            ("混合法热平衡与水当量", "./mixing"),
            ("冷却修正与温度外推", "./cooling"),
            ("电加热法与热损失", "./electrical"),
            ("多材料拟合与不确定度", "./fit"),
        )
    ]
    return Bonito.App(
        DOM.div(
            DOM.style(PAGE_STYLE),
            DOM.h1("固体比热容的测定"),
            DOM.div(links...),
            style = "padding:32px;background:#0b0f14;color:#eef3f8;min-height:100vh",
        );
        title = "固体比热容的测定",
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
    host = get(ENV, "SPECIFIC_HEAT_WEB_HOST", "127.0.0.1")
    port = parse(Int, get(ENV, "SPECIFIC_HEAT_WEB_PORT", "9393"))
    proxy_url = strip(get(ENV, "SPECIFIC_HEAT_WEB_PROXY_URL", "."))
    isempty(proxy_url) && (proxy_url = ".")
    server = Bonito.Server(host, port; proxy_url = proxy_url)
    Bonito.route!(server, "/__physics_health__" => health_app())
    Bonito.route!(server, "/" => index_app())
    Bonito.route!(server, "/mixing" => experiment_app("混合法热平衡与水当量", mixing_figure))
    Bonito.route!(server, "/cooling" => experiment_app("冷却修正与温度外推", cooling_figure))
    Bonito.route!(server, "/electrical" => experiment_app("电加热法与热损失", electrical_figure))
    Bonito.route!(server, "/fit" => experiment_app("多材料拟合与不确定度", fit_figure))
    println("固体比热容网页实验已启动：http://$(host):$(port)")
    wait(server)
end

if abspath(PROGRAM_FILE) == @__FILE__
    main()
end
