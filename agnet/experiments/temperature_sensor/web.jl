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

const PT100_R0 = 100.0
const PT100_ALPHA = 3.9083e-3
const PT100_BETA = -5.775e-7
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
const CJK_PROBE_TEXT = "温度传感器特性铂电阻热电偶标定灵敏度时间常数电桥拟合不确定度"
const HEALTH_MARKER = "physics-experiment:temperature-sensor"
const WGL_SHADER_FILES = (
    "mesh.frag", "mesh.vert", "particles.vert", "sprites.frag",
    "sprites.vert", "volume.frag", "volume.vert", "voxel.frag", "voxel.vert",
)

function load_packaged_wgl_shaders!()
    asset_dir = normpath(joinpath(Sys.BINDIR, "..", "share", "photoelectric", "wglmakie_assets"))
    isdir(asset_dir) || return false
    for name in WGL_SHADER_FILES
        path = joinpath(asset_dir, name)
        isfile(path) || error("缺少 WGLMakie 着色器文件：$(path)")
        WGLMakie.ALL_SHADERS[name] = read(path, String)
    end
    return true
end

function font_supports_cjk(path)
    try
        font = WGLMakie.Makie.FreeTypeAbstraction.FTFont(String(path))
        return all(ch -> WGLMakie.Makie.FreeTypeAbstraction.glyph_index(font, ch) != 0, CJK_PROBE_TEXT)
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
        return first_cjk_font([strip(line) for line in split(output, '\n') if !isempty(strip(line))])
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
        "/System/Library/Fonts/PingFang.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc", fontconfig_match("Noto Sans CJK SC:lang=zh-cn"),
    ])
    isnothing(regular) && error("未找到中文字体，请通过 PHYSICS_CJK_FONT 指定。")
    bold = first_cjk_font([
        get(ENV, "PHYSICS_CJK_FONT", ""), runtime_font, bundled_font, julia_font,
        isempty(get(ENV, "WINDIR", "")) ? "" : joinpath(ENV["WINDIR"], "Fonts", "msyhbd.ttc"),
        "/System/Library/Fonts/PingFang.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        fontconfig_match("Noto Sans CJK SC Bold:lang=zh-cn"),
    ])
    isnothing(bold) && (bold = regular)
    return (; regular, bold)
end

function configure_theme!()
    fonts = cjk_font_family()
    set_theme!(Theme(
        fontsize = 14, font = fonts.regular, fonts = (; regular = fonts.regular, bold = fonts.bold),
        textcolor = :white, backgroundcolor = RGBf(0.045, 0.052, 0.065),
        Axis = (backgroundcolor = PANEL_BG, xgridcolor = (:white, 0.07), ygridcolor = (:white, 0.07),
                spinecolor = (:white, 0.18), xtickcolor = (:white, 0.25), ytickcolor = (:white, 0.25),
                topspinevisible = false, rightspinevisible = false),
    ))
end

function base_figure()
    configure_theme!()
    figure = Figure(size = (FIGURE_WIDTH, FIGURE_HEIGHT), figure_padding = (18, 18, 22, 32))
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
    slider = Slider(grid[row, 2], range = range, startvalue = startvalue, update_while_dragging = false)
    Label(grid[row, 3], lift(formatter, slider.value), halign = :left)
    colsize!(grid, 1, Relative(0.19)); colsize!(grid, 2, Relative(0.65)); colsize!(grid, 3, Relative(0.16))
    rowsize!(grid, row, 21); rowgap!(grid, 3)
    return slider
end

function add_metrics!(grid, values, detail)
    for (column, value) in enumerate(values)
        Label(grid[1, column], value, halign = :left, fontsize = 13)
        colsize!(grid, column, Relative(0.25))
    end
    Label(grid[2, 1:4], detail, color = MUTED, halign = :left, fontsize = 12.5, tellwidth = false)
    rowsize!(grid, 1, 28); rowsize!(grid, 2, 66); rowgap!(grid, 8)
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
    play_button = Button(button_grid[1, 1], label = "播放", height = 31, buttoncolor = BUTTON_BG, labelcolor = :white)
    reset_button = Button(button_grid[2, 1], label = "重置", height = 31, buttoncolor = BUTTON_BG, labelcolor = :white)
    rowsize!(button_grid, 1, 31); rowsize!(button_grid, 2, 31); rowgap!(button_grid, 8); colsize!(grid, 4, Fixed(116))
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
                    set_close_to!(playback_slider, playback_values[mod1(index + step, length(playback_values))])
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
    xf, yf = Float64.(x), Float64.(y)
    xbar, ybar = sum(xf) / length(xf), sum(yf) / length(yf)
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

pt100_resistance(t; r0 = PT100_R0, alpha = PT100_ALPHA, beta = PT100_BETA) =
    Float64(r0) * (1.0 + Float64(alpha) * Float64(t) + Float64(beta) * Float64(t)^2)

pt100_sensitivity(t; r0 = PT100_R0, alpha = PT100_ALPHA, beta = PT100_BETA) =
    Float64(r0) * (Float64(alpha) + 2.0 * Float64(beta) * Float64(t))

function pt100_temperature(resistance; r0 = PT100_R0, alpha = PT100_ALPHA, beta = PT100_BETA)
    ratio = Float64(resistance) / Float64(r0)
    discriminant = Float64(alpha)^2 - 4.0 * Float64(beta) * (1.0 - ratio)
    discriminant >= 0 || throw(ArgumentError("电阻值超出当前 Pt100 正温区模型"))
    return (-Float64(alpha) + sqrt(discriminant)) / (2.0 * Float64(beta))
end

function calibration_model(max_temperature, point_count, zero_offset, noise_ohm, curvature_ohm, current_ma)
    tmax = Float64(max_temperature)
    n = Int(round(point_count))
    tmax > 0 || throw(ArgumentError("标定上限必须大于 0 ℃"))
    n >= 5 || throw(ArgumentError("标定点数至少为 5"))
    temperatures = collect(range(0.0, tmax; length = n))
    pattern = [0.00, 0.74, -0.52, 0.31, -0.68, 0.46, -0.23, 0.61, -0.39, 0.18, -0.57, 0.35]
    normalized = temperatures ./ tmax
    reference = pt100_resistance.(temperatures)
    measured = reference .+ Float64(zero_offset) .+ Float64(curvature_ohm) .* normalized .* (normalized .- 1.0) .+
               Float64(noise_ohm) .* [pattern[mod1(i, length(pattern))] for i in eachindex(temperatures)]
    fit = linear_fit(temperatures, measured)
    inferred_temperatures = (measured .- fit.intercept) ./ fit.slope
    temperature_errors = inferred_temperatures .- temperatures
    curve_temperatures = collect(range(0.0, tmax; length = 240))
    curve_reference = pt100_resistance.(curve_temperatures)
    curve_fit = fit.intercept .+ fit.slope .* curve_temperatures
    midpoint = tmax / 2.0
    current_a = Float64(current_ma) * 1.0e-3
    self_heating_mw = 1000.0 * current_a^2 * pt100_resistance(midpoint)
    return (; temperatures, reference, measured, fit, inferred_temperatures, temperature_errors,
            curve_temperatures, curve_reference, curve_fit, midpoint, self_heating_mw,
            max_temperature_error = maximum(abs.(temperature_errors)))
end

function response_model(current_time, initial_temperature, bath_temperature, tau_s, sample_interval, noise_c)
    t0, tb, tau = Float64(initial_temperature), Float64(bath_temperature), Float64(tau_s)
    tb > t0 || throw(ArgumentError("阶跃响应页面要求恒温槽温度高于初温"))
    tau > 0 || throw(ArgumentError("时间常数必须大于零"))
    interval = Float64(sample_interval)
    interval > 0 || throw(ArgumentError("采样间隔必须大于零"))
    duration = max(6.0 * tau, Float64(current_time), 10.0)
    curve_times = collect(range(0.0, duration; length = 300))
    curve_temperatures = tb .+ (t0 - tb) .* exp.(-curve_times ./ tau)
    sample_times = collect(0.0:interval:duration)
    pattern = [0.00, 0.58, -0.44, 0.27, -0.61, 0.39, -0.19, 0.49]
    ideal_samples = tb .+ (t0 - tb) .* exp.(-sample_times ./ tau)
    measured_samples = ideal_samples .+ Float64(noise_c) .* [pattern[mod1(i, length(pattern))] for i in eachindex(sample_times)]
    normalized_excess = clamp.((tb .- measured_samples) ./ (tb - t0), 1.0e-6, 1.0)
    fit = linear_fit(sample_times, log.(normalized_excess))
    fitted_tau = -1.0 / fit.slope
    now = clamp(Float64(current_time), 0.0, duration)
    current_temperature = tb + (t0 - tb) * exp(-now / tau)
    return (; t0, tb, tau, duration, curve_times, curve_temperatures, sample_times, measured_samples,
            normalized_excess, fit, fitted_tau, now, current_temperature,
            t63 = tau, t90 = log(10.0) * tau, current_fraction = (current_temperature - t0) / (tb - t0))
end

function bridge_model(sensor_temperature, balance_temperature, supply_voltage, lead_resistance, gain, self_heating_k_per_mw)
    ts, tb = Float64(sensor_temperature), Float64(balance_temperature)
    supply = Float64(supply_voltage)
    supply > 0 || throw(ArgumentError("电桥电源必须大于零"))
    lead = Float64(lead_resistance)
    lead >= 0 || throw(ArgumentError("导线电阻不能为负"))
    fixed = 100.0
    balance_resistance = pt100_resistance(tb)
    nominal_resistance = pt100_resistance(ts)
    sensor_branch = nominal_resistance + 2.0 * lead
    current_a = supply / (fixed + sensor_branch)
    self_heating_mw = 1000.0 * current_a^2 * nominal_resistance
    actual_temperature = ts + Float64(self_heating_k_per_mw) * self_heating_mw
    actual_resistance = pt100_resistance(actual_temperature)
    measured_branch = actual_resistance + 2.0 * lead
    bridge_output = supply * (measured_branch / (fixed + measured_branch) - balance_resistance / (fixed + balance_resistance))
    amplified_output = Float64(gain) * bridge_output
    ratio = bridge_output / supply + balance_resistance / (fixed + balance_resistance)
    inferred_branch = fixed * ratio / (1.0 - ratio)
    uncorrected_temperature = pt100_temperature(inferred_branch)
    corrected_temperature = pt100_temperature(inferred_branch - 2.0 * lead)
    scan_temperatures = collect(range(0.0, 150.0; length = 240))
    scan_resistances = pt100_resistance.(scan_temperatures) .+ 2.0 .* lead
    scan_outputs = Float64(gain) .* supply .* (scan_resistances ./ (fixed .+ scan_resistances) .-
                   balance_resistance / (fixed + balance_resistance))
    linear_sensitivity = Float64(gain) * supply * fixed * pt100_sensitivity(ts) / (fixed + nominal_resistance)^2
    return (; ts, tb, nominal_resistance, actual_resistance, actual_temperature, balance_resistance,
            bridge_output, amplified_output, self_heating_mw, uncorrected_temperature, corrected_temperature,
            scan_temperatures, scan_outputs, linear_sensitivity,
            lead_error = uncorrected_temperature - actual_temperature,
            corrected_error = corrected_temperature - actual_temperature)
end

function uncertainty_model(point_count, noise_ohm, hysteresis_ohm, standard_u_c, resistance_u_ohm, self_heating_u_c)
    n = Int(round(point_count))
    n >= 5 || throw(ArgumentError("重复标定至少需要 5 个温度点"))
    temperatures = collect(range(0.0, 100.0; length = n))
    pattern = [0.00, 0.67, -0.48, 0.29, -0.59, 0.42, -0.22, 0.54, -0.34, 0.17, -0.45, 0.31]
    noise = Float64(noise_ohm) .* [pattern[mod1(i, length(pattern))] for i in eachindex(temperatures)]
    reference = pt100_resistance.(temperatures)
    heating = reference .- Float64(hysteresis_ohm) / 2.0 .+ noise
    cooling = reference .+ Float64(hysteresis_ohm) / 2.0 .- reverse(noise)
    x = vcat(temperatures, temperatures)
    y = vcat(heating, cooling)
    fit = linear_fit(x, y)
    fitted_line = fit.intercept .+ fit.slope .* temperatures
    residual_heating = heating .- fitted_line
    residual_cooling = cooling .- fitted_line
    fit_u_c = sqrt(sum(abs2, fit.residuals) / (length(fit.residuals) - 2)) / abs(fit.slope * sqrt(length(x)))
    dmm_u_c = Float64(resistance_u_ohm) / abs(fit.slope)
    hysteresis_u_c = Float64(hysteresis_ohm) / (sqrt(12.0) * abs(fit.slope))
    components = [fit_u_c, Float64(standard_u_c), dmm_u_c, hysteresis_u_c, Float64(self_heating_u_c)]
    combined_u_c = sqrt(sum(abs2, components))
    expanded_u_c = 2.0 * combined_u_c
    labels = ["拟合重复性", "标准温度", "电阻测量", "滞后", "自热"]
    return (; temperatures, heating, cooling, fit, fitted_line, residual_heating, residual_cooling,
            components, labels, combined_u_c, expanded_u_c,
            max_residual_c = maximum(abs.(fit.residuals)) / abs(fit.slope))
end

function calibration_figure()
    figure, controls, metrics = base_figure()
    characteristic_axis = Axis(figure[1, 1], title = "Pt100 静态标定曲线", xlabel = "标准温度 t₉₀ / ℃", ylabel = "电阻 R / Ω")
    error_axis = Axis(figure[1, 2], title = "线性标定的温度残差", xlabel = "标准温度 t₉₀ / ℃", ylabel = "温度误差 Δt / ℃")
    tmax = add_slider!(controls, 1, "标定上限", 40:10:200, 100, v -> @sprintf("%.0f ℃", v))
    points = add_slider!(controls, 2, "标定点数", 5:1:12, 9, v -> @sprintf("%.0f 点", v))
    offset = add_slider!(controls, 3, "零点偏移", -1.0:0.05:1.0, 0.20, v -> @sprintf("%+.2f Ω", v))
    noise = add_slider!(controls, 4, "电阻噪声", 0.0:0.01:0.20, 0.04, v -> @sprintf("%.2f Ω", v))
    curvature = add_slider!(controls, 5, "附加非线性", 0.0:0.02:0.80, 0.20, v -> @sprintf("%.2f Ω", v))
    current = add_slider!(controls, 6, "测量电流", 0.1:0.1:2.0, 1.0, v -> @sprintf("%.1f mA", v))
    data = lift(tmax.value, points.value, offset.value, noise.value, curvature.value, current.value) do a,b,c,d,e,f
        calibration_model(a,b,c,d,e,f)
    end
    lines!(characteristic_axis, lift(v -> v.curve_temperatures, data), lift(v -> v.curve_reference, data), color = CYAN, linewidth = 2.7, label = "IEC 60751 参考")
    lines!(characteristic_axis, lift(v -> v.curve_temperatures, data), lift(v -> v.curve_fit, data), color = AMBER, linewidth = 2.3, linestyle = :dash, label = "线性拟合")
    scatter!(characteristic_axis, lift(v -> v.temperatures, data), lift(v -> v.measured, data), color = PINK, markersize = 11, label = "测量点")
    axislegend(characteristic_axis, position = :lt, framevisible = false, labelsize = 10)
    hlines!(error_axis, [0.0], color = MUTED, linewidth = 1.5)
    lines!(error_axis, lift(v -> v.temperatures, data), lift(v -> v.temperature_errors, data), color = VIOLET, linewidth = 2.5)
    scatter!(error_axis, lift(v -> v.temperatures, data), lift(v -> v.temperature_errors, data), color = AMBER, markersize = 10)
    values = (
        lift(v -> @sprintf("S = %.5f Ω/K", v.fit.slope), data),
        lift(v -> @sprintf("R₀,拟 = %.3f Ω", v.fit.intercept), data),
        lift(v -> @sprintf("max|Δt| = %.3f ℃", v.max_temperature_error), data),
        lift(v -> @sprintf("P自热 = %.3f mW", v.self_heating_mw), data),
    )
    detail = lift(data) do v
        @sprintf("Pt100（t≥0 ℃）：R=R₀(1+At+Bt²)，A=3.9083×10⁻³ K⁻¹，B=-5.775×10⁻⁷ K⁻²。\n当前线性拟合 R=%.4f+%.6ft，R²=%.6f；非线性残差与零偏、噪声和自热需分开评估。", v.fit.intercept, v.fit.slope, v.fit.r_squared)
    end
    add_metrics!(metrics, values, detail)
    bind_playback!(controls, 7, tmax, 40:10:200, [(tmax,100),(points,9),(offset,0.20),(noise,0.04),(curvature,0.20),(current,1.0)])
    return figure
end

function response_figure()
    figure, controls, metrics = base_figure()
    response_axis = Axis(figure[1, 1], title = "温度阶跃响应", xlabel = "时间 t / s", ylabel = "探头温度 T / ℃")
    fit_axis = Axis(figure[1, 2], title = "一阶模型半对数拟合", xlabel = "时间 t / s", ylabel = "ln[(Tₑ-T)/(Tₑ-T₀)]")
    time = add_slider!(controls, 1, "演示时刻", 0:1:180, 0, v -> @sprintf("%.0f s", v))
    initial = add_slider!(controls, 2, "探头初温", 0:1:30, 20, v -> @sprintf("%.0f ℃", v))
    bath = add_slider!(controls, 3, "恒温槽温度", 40:2:100, 80, v -> @sprintf("%.0f ℃", v))
    tau = add_slider!(controls, 4, "时间常数 τ", 5:1:40, 18, v -> @sprintf("%.0f s", v))
    interval = add_slider!(controls, 5, "采样间隔", 2:1:12, 5, v -> @sprintf("%.0f s", v))
    noise = add_slider!(controls, 6, "温度噪声", 0.0:0.02:0.40, 0.10, v -> @sprintf("%.2f ℃", v))
    data = lift(time.value, initial.value, bath.value, tau.value, interval.value, noise.value) do a,b,c,d,e,f
        response_model(a,b,c,d,e,f)
    end
    lines!(response_axis, lift(v -> v.curve_times, data), lift(v -> v.curve_temperatures, data), color = CYAN, linewidth = 2.8, label = "一阶响应")
    scatter!(response_axis, lift(v -> v.sample_times, data), lift(v -> v.measured_samples, data), color = PINK, markersize = 8, label = "采样")
    scatter!(response_axis, lift(v -> [v.now], data), lift(v -> [v.current_temperature], data), color = AMBER, markersize = 16, label = "当前")
    hlines!(response_axis, lift(v -> [v.t0 + 0.6321205588*(v.tb-v.t0)], data), color = GREEN, linestyle = :dash, linewidth = 1.8, label = "63.2%")
    axislegend(response_axis, position = :rb, framevisible = false, labelsize = 10)
    scatter!(fit_axis, lift(v -> v.sample_times, data), lift(v -> log.(v.normalized_excess), data), color = VIOLET, markersize = 8)
    lines!(fit_axis, lift(v -> v.sample_times, data), lift(v -> v.fit.predicted, data), color = AMBER, linewidth = 2.4)
    values = (
        lift(v -> @sprintf("T(t) = %.2f ℃", v.current_temperature), data),
        lift(v -> @sprintf("响应进度 = %.1f%%", 100.0 * v.current_fraction), data),
        lift(v -> @sprintf("τ拟 = %.2f s", v.fitted_tau), data),
        lift(v -> @sprintf("t₉₀ = %.2f s", v.t90), data),
    )
    detail = lift(data) do v
        @sprintf("一阶传感器：T(t)=Tₑ+(T₀-Tₑ)e⁻ᵗ/ᵗ；t=τ 时完成 63.2%% 阶跃，t₉₀=τln10。\n半对数直线斜率=-1/τ，当前拟合斜率 %.5f s⁻¹，R²=%.6f。", v.fit.slope, v.fit.r_squared)
    end
    add_metrics!(metrics, values, detail)
    bind_playback!(controls, 7, time, 0:1:180, [(time,0),(initial,20),(bath,80),(tau,18),(interval,5),(noise,0.10)]; step = 2)
    return figure
end

function bridge_figure()
    figure, controls, metrics = base_figure()
    output_axis = Axis(figure[1, 1], title = "Pt100 不平衡电桥输出", xlabel = "探头温度 t / ℃", ylabel = "放大后输出 Uₒ / V")
    error_axis = Axis(figure[1, 2], title = "导线电阻与自热偏差", xlabel = "估计温度 / ℃", ylabel = "偏差 Δt / ℃")
    temperature = add_slider!(controls, 1, "探头温度", 0:1:150, 60, v -> @sprintf("%.0f ℃", v))
    balance = add_slider!(controls, 2, "平衡温度", 0:5:100, 0, v -> @sprintf("%.0f ℃", v))
    supply = add_slider!(controls, 3, "电桥电源", 0.5:0.1:5.0, 2.0, v -> @sprintf("%.1f V", v))
    lead = add_slider!(controls, 4, "单根导线电阻", 0.0:0.02:1.0, 0.20, v -> @sprintf("%.2f Ω", v))
    gain = add_slider!(controls, 5, "仪表放大倍数", 1:1:20, 10, v -> @sprintf("×%.0f", v))
    self_heating = add_slider!(controls, 6, "自热系数", 0.0:0.02:0.50, 0.10, v -> @sprintf("%.2f K/mW", v))
    data = lift(temperature.value, balance.value, supply.value, lead.value, gain.value, self_heating.value) do a,b,c,d,e,f
        bridge_model(a,b,c,d,e,f)
    end
    lines!(output_axis, lift(v -> v.scan_temperatures, data), lift(v -> v.scan_outputs, data), color = CYAN, linewidth = 2.8)
    scatter!(output_axis, lift(v -> [v.ts], data), lift(v -> [v.amplified_output], data), color = AMBER, markersize = 16)
    vlines!(output_axis, lift(v -> [v.tb], data), color = MUTED, linestyle = :dash, linewidth = 1.7)
    hlines!(error_axis, [0.0], color = MUTED, linewidth = 1.5)
    scatter!(error_axis, lift(v -> [v.uncorrected_temperature, v.corrected_temperature], data),
             lift(v -> [v.lead_error, v.corrected_error], data), color = [PINK, GREEN], markersize = 17)
    lines!(error_axis, lift(v -> [v.uncorrected_temperature, v.corrected_temperature], data),
           lift(v -> [v.lead_error, v.corrected_error], data), color = VIOLET, linewidth = 2.0)
    values = (
        lift(v -> @sprintf("R(T) = %.3f Ω", v.actual_resistance), data),
        lift(v -> @sprintf("Uₒ = %.4f V", v.amplified_output), data),
        lift(v -> @sprintf("Sᵤ = %.3f V/K", v.linear_sensitivity), data),
        lift(v -> @sprintf("二线制偏差 = %+.3f ℃", v.lead_error), data),
    )
    detail = lift(data) do v
        @sprintf("电桥输出：Uₒ=G Uₛ[Rₛ/(R+Rₛ)-Rₑ/(R+Rₑ)]。二线制将 2rₗ 误当传感器电阻，三/四线制用导线补偿削弱该项。\n当前自热 %.3f mW 使敏感元温升 %.3f K；扣除导线后剩余偏差 %+.3f ℃。", v.self_heating_mw, v.actual_temperature-v.ts, v.corrected_error)
    end
    add_metrics!(metrics, values, detail)
    bind_playback!(controls, 7, temperature, 0:1:150, [(temperature,60),(balance,0),(supply,2.0),(lead,0.20),(gain,10),(self_heating,0.10)]; step = 2)
    return figure
end

function uncertainty_figure()
    figure, controls, metrics = base_figure()
    fit_axis = Axis(figure[1, 1], title = "升温/降温重复标定", xlabel = "标准温度 t₉₀ / ℃", ylabel = "Pt100 电阻 R / Ω")
    budget_axis = Axis(figure[1, 2], title = "温度标准不确定度分量", xlabel = "分量", ylabel = "u(t) / ℃", xticks = (1:5, ["重复", "标准", "电阻", "滞后", "自热"]))
    points = add_slider!(controls, 1, "每程标定点数", 5:1:12, 9, v -> @sprintf("%.0f 点", v))
    noise = add_slider!(controls, 2, "电阻重复性", 0.0:0.01:0.20, 0.05, v -> @sprintf("%.2f Ω", v))
    hysteresis = add_slider!(controls, 3, "升降温滞后", 0.0:0.02:0.60, 0.16, v -> @sprintf("%.2f Ω", v))
    standard_u = add_slider!(controls, 4, "标准温度 u", 0.01:0.01:0.20, 0.05, v -> @sprintf("%.2f ℃", v))
    resistance_u = add_slider!(controls, 5, "电阻测量 u", 0.001:0.001:0.050, 0.010, v -> @sprintf("%.3f Ω", v))
    self_heating_u = add_slider!(controls, 6, "自热修正 u", 0.00:0.01:0.20, 0.04, v -> @sprintf("%.2f ℃", v))
    data = lift(points.value, noise.value, hysteresis.value, standard_u.value, resistance_u.value, self_heating_u.value) do a,b,c,d,e,f
        uncertainty_model(a,b,c,d,e,f)
    end
    lines!(fit_axis, lift(v -> v.temperatures, data), lift(v -> v.fitted_line, data), color = AMBER, linewidth = 2.5, label = "联合拟合")
    scatter!(fit_axis, lift(v -> v.temperatures, data), lift(v -> v.heating, data), color = PINK, marker = :utriangle, markersize = 10, label = "升温")
    scatter!(fit_axis, lift(v -> v.temperatures, data), lift(v -> v.cooling, data), color = CYAN, marker = :dtriangle, markersize = 10, label = "降温")
    axislegend(fit_axis, position = :lt, framevisible = false, labelsize = 10)
    barplot!(budget_axis, 1:5, lift(v -> v.components, data), color = [CYAN, GREEN, AMBER, PINK, VIOLET])
    values = (
        lift(v -> @sprintf("S = %.5f Ω/K", v.fit.slope), data),
        lift(v -> @sprintf("R² = %.6f", v.fit.r_squared), data),
        lift(v -> @sprintf("uᶜ(t) = %.3f ℃", v.combined_u_c), data),
        lift(v -> @sprintf("U(k=2) = %.3f ℃", v.expanded_u_c), data),
    )
    detail = lift(data) do v
        @sprintf("按 GUM 方框和：uᶜ=√(u²ₐ+u²ᵇ+…)，扩展不确定度 U=kuᶜ。重复性与拟合属 A 类，标准温度、电阻示值、滞后和自热通常作 B 类。\n当前最大拟合残差等效为 %.3f ℃；报告须同时给出模型、温区、k 和各分量来源。", v.max_residual_c)
    end
    add_metrics!(metrics, values, detail)
    bind_playback!(controls, 7, hysteresis, 0.0:0.02:0.60, [(points,9),(noise,0.05),(hysteresis,0.16),(standard_u,0.05),(resistance_u,0.010),(self_heating_u,0.04)])
    return figure
end

function run_self_test()
    @assert isapprox(pt100_resistance(0.0), 100.0; atol = 1.0e-12)
    @assert isapprox(pt100_resistance(100.0), 138.5055; atol = 1.0e-4)
    @assert isapprox(pt100_temperature(pt100_resistance(80.0)), 80.0; atol = 1.0e-9)
    calibration = calibration_model(100.0, 9, 0.0, 0.0, 0.0, 1.0)
    @assert calibration.fit.slope > 0.37
    @assert calibration.fit.r_squared > 0.9999
    response = response_model(18.0, 20.0, 80.0, 18.0, 5.0, 0.0)
    @assert isapprox(response.current_fraction, 1.0 - exp(-1.0); atol = 1.0e-12)
    @assert isapprox(response.fitted_tau, 18.0; rtol = 1.0e-10)
    bridge = bridge_model(60.0, 0.0, 2.0, 0.2, 10.0, 0.0)
    @assert bridge.lead_error > 0.0
    @assert abs(bridge.corrected_error) < 1.0e-9
    budget = uncertainty_model(9, 0.05, 0.16, 0.05, 0.010, 0.04)
    @assert budget.combined_u_c > 0.0
    @assert isapprox(budget.expanded_u_c, 2.0 * budget.combined_u_c; atol = 1.0e-12)
    for builder in (calibration_figure, response_figure, bridge_figure, uncertainty_figure)
        @assert builder() isa Figure
    end
    @assert occursin(".temperature-sensor-lab", PAGE_STYLE)
    @assert occursin("pointerdown", CLIENT_STATUS_SCRIPT)
    @assert occursin("baseWinscale * layoutScale", CLIENT_STATUS_SCRIPT)
    @assert occursin("temperature-sensor-wgl-ready", CLIENT_STATUS_SCRIPT)
    println("温度传感器特性四个独立网页实验自检通过。")
end

const PAGE_STYLE = """
html, body { margin: 0; width: 100%; height: 100%; background: #0b0f14; color: #eef3f8; }
body { position: relative; overflow: hidden; font-family: 'Microsoft YaHei', 'Noto Sans CJK SC', sans-serif; }
.temperature-sensor-lab { position: absolute; left: 0; top: 0; width: $(FIGURE_WIDTH)px; height: $(FIGURE_HEIGHT)px;
    margin: 0; padding: 0; box-sizing: border-box; overflow: hidden; background: #0b0f14; transform-origin: 0 0; }
.temperature-sensor-diagnostic { position: fixed; left: 16px; right: 16px; bottom: 16px; z-index: 1002;
    display: none; padding: 10px 12px; color: #f7d7d7; background: rgba(64,20,28,.94);
    border: 1px solid rgba(255,85,105,.65); border-radius: 6px; font: 13px/1.5 ui-monospace,Consolas,monospace; white-space: pre-wrap; }
.temperature-sensor-diagnostic.visible { display: block; }
"""

const CLIENT_STATUS_SCRIPT = """
(() => {
    let ready = false, fitFrame = 0, layoutScale = 1;
    const parentWindow = window.parent || window;
    const send = (type, detail = "") => parentWindow.postMessage({ type, detail }, "*");
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
        const page = document.querySelector(".temperature-sensor-lab");
        if (!page) return;
        const viewport = window.visualViewport;
        const viewportWidth = Math.max(1, viewport ? viewport.width : (document.documentElement.clientWidth || window.innerWidth));
        const viewportHeight = Math.max(1, viewport ? viewport.height : (document.documentElement.clientHeight || window.innerHeight));
        const scale = Math.min(1.05, Math.max(1, viewportWidth - 12) / $(FIGURE_WIDTH), Math.max(1, viewportHeight - 8) / $(FIGURE_HEIGHT));
        const offsetX = (viewport ? viewport.offsetLeft : 0) + Math.max(0, (viewportWidth - $(FIGURE_WIDTH) * scale) / 2);
        const offsetY = (viewport ? viewport.offsetTop : 0) + Math.max(0, (viewportHeight - $(FIGURE_HEIGHT) * scale) / 2);
        layoutScale = scale;
        page.style.transform = "translate3d(" + offsetX + "px," + offsetY + "px,0) scale(" + scale + ")";
    };
    const scheduleFit = () => { if (fitFrame) cancelAnimationFrame(fitFrame); fitFrame = requestAnimationFrame(() => { fitFrame = 0; fitLayout(); }); };
    fitLayout(); requestAnimationFrame(fitLayout); window.addEventListener("resize", scheduleFit);
    window.addEventListener("orientationchange", scheduleFit);
    if (window.visualViewport) { window.visualViewport.addEventListener("resize", scheduleFit); window.visualViewport.addEventListener("scroll", scheduleFit); }
    if (window.ResizeObserver) { const observer = new ResizeObserver(scheduleFit); observer.observe(document.documentElement); observer.observe(document.body); }
    setTimeout(fitLayout, 250);
    for (const eventName of ["mousemove","mousedown","mouseup","pointerdown","pointermove","pointerup","pointercancel","wheel"])
        document.addEventListener(eventName, syncWGLPointerScale, { capture: true, passive: true });
    const showDiagnostic = detail => {
        let box = document.getElementById("temperature-sensor-diagnostic");
        if (!box) { box = document.createElement("div"); box.id = "temperature-sensor-diagnostic"; box.className = "temperature-sensor-diagnostic"; document.body.appendChild(box); }
        box.textContent = detail; box.classList.add("visible"); send("temperature-sensor-wgl-failed", detail);
    };
    const webglProbe = () => {
        try { const canvas = document.createElement("canvas"); if (canvas.getContext("webgl2", {antialias:true})) return "webgl2";
              if (canvas.getContext("webgl", {antialias:true}) || canvas.getContext("experimental-webgl")) return "webgl1"; }
        catch (error) { return "error: " + error.message; }
        return "none";
    };
    const glStatus = webglProbe();
    if (glStatus === "none" || glStatus.startsWith("error:")) { showDiagnostic("浏览器无法创建 WebGL 上下文：" + glStatus); return; }
    const startedAt = performance.now();
    const check = () => {
        const canvas = document.querySelector("canvas"), spinner = document.querySelector(".wglmakie-spinner");
        const spinnerVisible = Boolean(spinner && spinner.getClientRects().length > 0 && getComputedStyle(spinner).visibility !== "hidden");
        if (canvas && canvas.width > 0 && canvas.height > 0 && !spinnerVisible) { ready = true; send("temperature-sensor-wgl-ready", glStatus); return; }
        if (!ready && performance.now() - startedAt > 75000) { showDiagnostic("WGLMakie/Bonito 初始化超过 75 秒。\\nWebGL 状态：" + glStatus + "\\n页面地址：" + location.href); return; }
        window.setTimeout(check, 300);
    };
    window.addEventListener("error", event => showDiagnostic("浏览器脚本错误：" + event.message + "\\n" + event.filename + ":" + event.lineno));
    window.addEventListener("unhandledrejection", event => showDiagnostic("浏览器 Promise 错误：" + String(event.reason)));
    check();
})();
"""

function experiment_app(title, builder)
    return Bonito.App(; title = title) do
        DOM.div(DOM.style(PAGE_STYLE), DOM.div(builder(); class = "temperature-sensor-lab"), DOM.script(CLIENT_STATUS_SCRIPT))
    end
end

function index_app()
    links = [DOM.a(name; href = path, style = "color:#73d7cf;margin-right:24px") for (name,path) in (
        ("Pt100 静态标定与灵敏度", "./calibration"),
        ("阶跃响应与时间常数", "./response"),
        ("测量电桥、导线补偿与自热", "./bridge"),
        ("滞后、拟合与不确定度", "./uncertainty"),
    )]
    return Bonito.App(DOM.div(DOM.style(PAGE_STYLE), DOM.h1("温度传感器特性的测定"), DOM.div(links...),
        style = "padding:32px;background:#0b0f14;color:#eef3f8;min-height:100vh"); title = "温度传感器特性的测定")
end

health_app() = Bonito.App(DOM.pre(HEALTH_MARKER); title = HEALTH_MARKER)

function main()
    load_packaged_wgl_shaders!()
    WGLMakie.activate!(; use_html_widgets = true)
    configure_theme!()
    if "--self-test" in ARGS
        run_self_test(); return
    end
    host = get(ENV, "TEMPERATURE_SENSOR_WEB_HOST", "127.0.0.1")
    port = parse(Int, get(ENV, "TEMPERATURE_SENSOR_WEB_PORT", "9395"))
    proxy_url = strip(get(ENV, "TEMPERATURE_SENSOR_WEB_PROXY_URL", ".")); isempty(proxy_url) && (proxy_url = ".")
    server = Bonito.Server(host, port; proxy_url = proxy_url)
    Bonito.route!(server, "/__physics_health__" => health_app())
    Bonito.route!(server, "/" => index_app())
    Bonito.route!(server, "/calibration" => experiment_app("Pt100 静态标定与灵敏度", calibration_figure))
    Bonito.route!(server, "/response" => experiment_app("阶跃响应与时间常数", response_figure))
    Bonito.route!(server, "/bridge" => experiment_app("测量电桥、导线补偿与自热", bridge_figure))
    Bonito.route!(server, "/uncertainty" => experiment_app("滞后、拟合与不确定度", uncertainty_figure))
    println("温度传感器特性网页实验已启动：http://$(host):$(port)")
    wait(server)
end

if abspath(PROGRAM_FILE) == @__FILE__
    main()
end
