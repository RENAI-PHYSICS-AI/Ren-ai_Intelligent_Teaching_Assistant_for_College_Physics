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
const MU0 = 4 * pi * 1.0e-7
const CYAN = RGBf(0.18, 0.78, 0.92)
const PINK = RGBf(0.94, 0.35, 0.50)
const AMBER = RGBf(1.00, 0.72, 0.24)
const GREEN = RGBf(0.36, 0.82, 0.55)
const VIOLET = RGBf(0.61, 0.48, 0.92)
const MUTED = RGBf(0.58, 0.62, 0.70)
const PANEL_BG = RGBf(0.075, 0.085, 0.105)
const BUTTON_BG = RGBf(0.13, 0.15, 0.19)
const CJK_PROBE_TEXT = "铁磁滞回线磁感应强度矫顽力剩磁示波器退磁损耗不确定度"
const HEALTH_MARKER = "physics-experiment:magnetic-hysteresis"
const WGL_SHADER_FILES = (
    "mesh.frag", "mesh.vert", "particles.vert", "sprites.frag", "sprites.vert",
    "volume.frag", "volume.vert", "voxel.frag", "voxel.vert",
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
        fontconfig_match("Noto Sans CJK SC:lang=zh-cn"),
    ])
    isnothing(regular) && error("未找到包含中文字形的字体，请设置 PHYSICS_CJK_FONT。")
    bold = first_cjk_font([
        get(ENV, "PHYSICS_CJK_FONT", ""), runtime_font, bundled_font, julia_font,
        isempty(get(ENV, "WINDIR", "")) ? "" : joinpath(ENV["WINDIR"], "Fonts", "msyhbd.ttc"),
        "/System/Library/Fonts/PingFang.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
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
            spinecolor = (:white, 0.18), xtickcolor = (:white, 0.25), ytickcolor = (:white, 0.25),
            topspinevisible = false, rightspinevisible = false,
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
    Label(grid[2, 1:4], detail, color = MUTED, halign = :left, fontsize = 12.5, tellwidth = false)
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
    play_button = Button(button_grid[1, 1], label = "播放", height = 31, buttoncolor = BUTTON_BG, labelcolor = :white)
    reset_button = Button(button_grid[2, 1], label = "重置", height = 31, buttoncolor = BUTTON_BG, labelcolor = :white)
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

function loop_curve(hmax, hc, br, bs; points = 361)
    Float64(hmax) > Float64(hc) > 0 || throw(ArgumentError("最大磁场必须大于矫顽力"))
    0 < Float64(br) < Float64(bs) || throw(ArgumentError("剩磁必须位于 0 与饱和磁感应强度之间"))
    theta = collect(range(0.0, 2 * pi; length = points))
    h = Float64(hmax) .* sin.(theta)
    scale = Float64(hc) / atanh(Float64(br) / Float64(bs))
    branch = ifelse.(cos.(theta) .< 0.0, 1.0, -1.0)
    b = Float64(bs) .* tanh.((h .+ branch .* Float64(hc)) ./ scale)
    return (; theta, h, b, scale, area = abs(sum((b[1:end-1] .+ b[2:end]) .* diff(h)) / 2))
end

function loop_figure()
    figure, controls, metrics = base_figure()
    loop_axis = Axis(figure[1, 1], title = "铁磁材料 B-H 磁滞回线", xlabel = "磁场强度 H / A·m⁻¹", ylabel = "磁感应强度 B / T")
    time_axis = Axis(figure[1, 2], title = "交变磁化过程", xlabel = "归一化相位 φ / 2π", ylabel = "H/Hₘ 与 B/Bₛ")

    hmax = add_slider!(controls, 1, "最大磁场 Hₘ", 400:20:1600, 1000, value -> @sprintf("%.0f A/m", value))
    hc = add_slider!(controls, 2, "矫顽力 Hc", 40:5:300, 120, value -> @sprintf("%.0f A/m", value))
    br = add_slider!(controls, 3, "剩磁 Br", 0.20:0.02:0.90, 0.60, value -> @sprintf("%.2f T", value))
    bs = add_slider!(controls, 4, "饱和磁感应 Bs", 0.80:0.02:1.60, 1.20, value -> @sprintf("%.2f T", value))
    phase = add_slider!(controls, 5, "磁化相位 φ", 0:1:360, 0, value -> @sprintf("%.0f°", value))

    data = lift(hmax.value, hc.value, br.value, bs.value) do hm, coercive, remanence, saturation
        safe_br = min(Float64(remanence), Float64(saturation) - 0.02)
        loop_curve(Float64(hm), Float64(coercive), safe_br, Float64(saturation))
    end
    lines!(loop_axis, lift(value -> value.h, data), lift(value -> value.b, data), color = CYAN, linewidth = 3.0)
    scatter!(loop_axis,
        lift(data, phase.value) do value, p; [value.h[clamp(Int(p) + 1, 1, length(value.h))]] end,
        lift(data, phase.value) do value, p; [value.b[clamp(Int(p) + 1, 1, length(value.b))]] end,
        color = AMBER, markersize = 18,
    )
    lines!(time_axis, lift(value -> value.theta ./ (2 * pi), data), lift(value -> value.h ./ maximum(abs, value.h), data), color = PINK, linewidth = 2.4, label = "H/Hₘ")
    lines!(time_axis, lift(value -> value.theta ./ (2 * pi), data), lift(value -> value.b ./ maximum(abs, value.b), data), color = GREEN, linewidth = 2.4, label = "B/Bₛ")
    vlines!(time_axis, lift(p -> [Float64(p) / 360.0], phase.value), color = AMBER, linewidth = 2.0)
    axislegend(time_axis, position = :rb, framevisible = false)

    values = (
        lift(value -> @sprintf("Hc = %.0f A/m", hc.value[]), hc.value),
        lift(value -> @sprintf("Br = %.2f T", br.value[]), br.value),
        lift(value -> @sprintf("μr,max ≈ %.0f", maximum(abs.(value.b ./ (MU0 .* (value.h .+ 1.0))))), data),
        lift(value -> @sprintf("回线面积 = %.1f J/m³", value.area), data),
    )
    detail = lift(data) do value
        @sprintf("回线与 H 轴交点给出矫顽力 Hc，与 B 轴交点给出剩磁 Br；闭合回线面积 ∮H dB（等价于 ∮B dH 的绝对值）表示每周期单位体积磁滞损耗。当前支路尺度 a=%.1f A/m。", value.scale)
    end
    add_metrics!(metrics, values, detail)
    bind_playback!(controls, 6, phase, 0:1:360, [(hmax, 1000), (hc, 120), (br, 0.60), (bs, 1.20), (phase, 0)])
    return figure
end

function apparatus_model(n1, n2, resistance, capacitance_uf, drive_v, phase_deg)
    turns_primary = Float64(n1)
    turns_secondary = Float64(n2)
    r = Float64(resistance)
    c = Float64(capacitance_uf) * 1.0e-6
    voltage = Float64(drive_v)
    t = collect(range(0.0, 1.0; length = 361))
    current = voltage .* sin.(2 * pi .* t) ./ r
    h = turns_primary .* current ./ 0.18
    base = loop_curve(maximum(abs, h), 0.12 * maximum(abs, h), 0.55, 1.10)
    b = base.b
    induced = -turns_secondary * 2.0e-4 .* [diff(b); b[end] - b[end-1]] .* 360.0
    uy = b .* turns_secondary .* 2.0e-4 ./ max(r * c, eps())
    index = clamp(Int(phase_deg) + 1, 1, length(t))
    return (; t, current, h, b, induced, uy, index, field_factor = turns_primary / 0.18, integrator_factor = r * c / (turns_secondary * 2.0e-4))
end

function apparatus_figure()
    figure, controls, metrics = base_figure()
    signal_axis = Axis(figure[1, 1], title = "励磁与感应信号", xlabel = "周期相位 t/T", ylabel = "归一化信号")
    scope_axis = Axis(figure[1, 2], title = "示波器 X-Y 法复现 B-H 回线", xlabel = "X ∝ H", ylabel = "Y ∝ B")

    n1 = add_slider!(controls, 1, "励磁匝数 N₁", 100:10:500, 300, value -> @sprintf("%.0f 匝", value))
    n2 = add_slider!(controls, 2, "测量匝数 N₂", 50:10:300, 150, value -> @sprintf("%.0f 匝", value))
    resistance = add_slider!(controls, 3, "采样电阻 R", 40:5:200, 100, value -> @sprintf("%.0f Ω", value))
    capacitance = add_slider!(controls, 4, "积分电容 C", 1.0:0.5:10.0, 4.0, value -> @sprintf("%.1f μF", value))
    drive = add_slider!(controls, 5, "励磁电压 U", 1.0:0.2:6.0, 3.0, value -> @sprintf("%.1f V", value))
    phase = add_slider!(controls, 6, "扫描相位", 0:1:360, 0, value -> @sprintf("%.0f°", value))

    data = lift(n1.value, n2.value, resistance.value, capacitance.value, drive.value, phase.value) do a, b, r, c, u, p
        apparatus_model(a, b, r, c, u, p)
    end
    lines!(signal_axis, lift(value -> value.t, data), lift(value -> value.h ./ maximum(abs, value.h), data), color = PINK, linewidth = 2.4, label = "H/Hₘ")
    lines!(signal_axis, lift(value -> value.t, data), lift(value -> value.induced ./ maximum(abs, value.induced), data), color = CYAN, linewidth = 2.2, label = "感应电压")
    lines!(signal_axis, lift(value -> value.t, data), lift(value -> value.uy ./ maximum(abs, value.uy), data), color = GREEN, linewidth = 2.2, label = "积分输出∝B")
    vlines!(signal_axis, lift(value -> [value.t[value.index]], data), color = AMBER, linewidth = 2.0)
    axislegend(signal_axis, position = :rb, framevisible = false, labelsize = 10)
    lines!(scope_axis, lift(value -> value.h, data), lift(value -> value.b, data), color = VIOLET, linewidth = 3.0)
    scatter!(scope_axis, lift(value -> [value.h[value.index]], data), lift(value -> [value.b[value.index]], data), color = AMBER, markersize = 18)

    values = (
        lift(value -> @sprintf("Hₘ = %.0f A/m", maximum(abs, value.h)), data),
        lift(value -> @sprintf("Iₘ = %.1f mA", 1000 * maximum(abs, value.current)), data),
        lift(value -> @sprintf("Kₓ = %.1f A/(m·A)", value.field_factor), data),
        lift(value -> @sprintf("Kᵧ = %.3g T/V", value.integrator_factor), data),
    )
    detail = lift(data) do value
        @sprintf("环形样品近似 H=N₁I/l，次级线圈 e₂=-N₂A dB/dt；RC 积分后 Uᵧ≈-N₂AB/(RC)。X 通道取样励磁电流、Y 通道取积分电压即可显示 B-H 回线。当前相位 %.0f°。", 360 * value.t[value.index])
    end
    add_metrics!(metrics, values, detail)
    bind_playback!(controls, 7, phase, 0:1:360, [(n1, 300), (n2, 150), (resistance, 100), (capacitance, 4.0), (drive, 3.0), (phase, 0)])
    return figure
end

function demagnetization_model(initial_field, decay, cycles, hc, bs)
    ncycle = Int(cycles)
    amplitudes = Float64(initial_field) .* Float64(decay) .^ collect(0:12)
    residual = Float64(bs) .* tanh.(amplitudes ./ max(4 * Float64(hc), 1.0)) .* (-1.0) .^ collect(0:12)
    amplitude = amplitudes[ncycle + 1]
    effective_hc = min(Float64(hc), max(0.65 * amplitude, 1.0))
    br = min(0.75 * Float64(bs) * amplitude / Float64(initial_field), 0.95 * Float64(bs))
    loop = amplitude > effective_hc + 2 && br > 0.01 ? loop_curve(amplitude, effective_hc, max(br, 0.011), Float64(bs)) : (; theta = collect(range(0.0, 2 * pi; length = 361)), h = amplitude .* sin.(range(0.0, 2 * pi; length = 361)), b = zeros(361), scale = 0.0, area = 0.0)
    return (; amplitudes, residual, loop, ncycle, amplitude, final_residual = abs(residual[end]))
end

function demagnetization_figure()
    figure, controls, metrics = base_figure()
    loop_axis = Axis(figure[1, 1], title = "逐步减幅的交流退磁", xlabel = "磁场强度 H / A·m⁻¹", ylabel = "磁感应强度 B / T")
    decay_axis = Axis(figure[1, 2], title = "峰值磁场与剩磁衰减", xlabel = "退磁周期序号", ylabel = "归一化幅值")

    initial_field = add_slider!(controls, 1, "初始峰值 H₀", 600:20:1800, 1200, value -> @sprintf("%.0f A/m", value))
    decay = add_slider!(controls, 2, "每周期衰减 q", 0.55:0.01:0.90, 0.75, value -> @sprintf("%.2f", value))
    cycles = add_slider!(controls, 3, "退磁周期 n", 0:1:12, 0, value -> @sprintf("%.0f", value))
    hc = add_slider!(controls, 4, "材料矫顽力 Hc", 40:5:220, 100, value -> @sprintf("%.0f A/m", value))
    bs = add_slider!(controls, 5, "饱和磁感应 Bs", 0.80:0.02:1.50, 1.16, value -> @sprintf("%.2f T", value))

    data = lift(initial_field.value, decay.value, cycles.value, hc.value, bs.value) do h0, q, n, coercive, saturation
        demagnetization_model(h0, q, n, coercive, saturation)
    end
    lines!(loop_axis, lift(value -> value.loop.h, data), lift(value -> value.loop.b, data), color = CYAN, linewidth = 3.0)
    scatter!(decay_axis, lift(value -> collect(0:12), data), lift(value -> value.amplitudes ./ value.amplitudes[1], data), color = PINK, markersize = 10, label = "H峰/H₀")
    lines!(decay_axis, lift(value -> collect(0:12), data), lift(value -> abs.(value.residual) ./ maximum(abs, value.residual), data), color = GREEN, linewidth = 2.4, label = "|Br|/max")
    scatter!(decay_axis, lift(value -> [value.ncycle], data), lift(value -> [value.amplitudes[value.ncycle + 1] / value.amplitudes[1]], data), color = AMBER, markersize = 18)
    axislegend(decay_axis, position = :rt, framevisible = false)

    values = (
        lift(value -> @sprintf("n = %d", value.ncycle), data),
        lift(value -> @sprintf("H峰 = %.1f A/m", value.amplitude), data),
        lift(value -> @sprintf("当前回线面积 = %.1f J/m³", value.loop.area), data),
        lift(value -> @sprintf("末端剩磁 ≈ %.3f T", value.final_residual), data),
    )
    detail = lift(data) do value
        @sprintf("交流退磁通过反复翻转磁畴并缓慢降低磁场峰值，使工作点沿一系列缩小的磁滞回线逼近原点。第 %d 周期峰值为初始值的 %.3f。", value.ncycle, value.amplitude / value.amplitudes[1])
    end
    add_metrics!(metrics, values, detail)
    bind_playback!(controls, 6, cycles, 0:1:12, [(initial_field, 1200), (decay, 0.75), (cycles, 0), (hc, 100), (bs, 1.16)])
    return figure
end

function loss_model(bmax, frequency, exponent, kh, ke, noise_percent)
    f = collect(range(5.0, 200.0; length = 160))
    b = Float64(bmax)
    n = Float64(exponent)
    hysteresis_power = Float64(kh) .* f .* b^n
    eddy_power = Float64(ke) .* f .^ 2 .* b^2
    total = hysteresis_power .+ eddy_power
    pattern = sin.(collect(range(0.0, 8 * pi; length = length(f))))
    observed = total .* (1 .+ Float64(noise_percent) * 0.01 .* pattern)
    current_index = argmin(abs.(f .- Float64(frequency)))
    uncertainty = hypot(Float64(noise_percent), 1.2, 0.8, 1.5)
    return (; f, hysteresis_power, eddy_power, total, observed, current_index, b, n, uncertainty, loop_energy = total[current_index] / f[current_index])
end

function fit_figure()
    figure, controls, metrics = base_figure()
    loss_axis = Axis(figure[1, 1], title = "磁滞损耗与动态损耗分离", xlabel = "频率 f / Hz", ylabel = "功率损耗密度 P / W·m⁻³")
    steinmetz_axis = Axis(figure[1, 2], title = "Steinmetz 指数检验", xlabel = "ln(Bₘ/T)", ylabel = "ln(Wₕ/(J·m⁻³))")

    bmax = add_slider!(controls, 1, "峰值磁感应 Bₘ", 0.20:0.02:1.40, 1.00, value -> @sprintf("%.2f T", value))
    frequency = add_slider!(controls, 2, "工作频率 f", 5:5:200, 50, value -> @sprintf("%.0f Hz", value))
    exponent = add_slider!(controls, 3, "Steinmetz 指数 n", 1.20:0.02:2.20, 1.60, value -> @sprintf("%.2f", value))
    kh = add_slider!(controls, 4, "磁滞系数 kₕ", 20:2:160, 80, value -> @sprintf("%.0f", value))
    ke = add_slider!(controls, 5, "涡流系数 kₑ", 0.01:0.01:0.30, 0.10, value -> @sprintf("%.2f", value))
    noise = add_slider!(controls, 6, "测量噪声", 0.0:0.2:5.0, 1.0, value -> @sprintf("%.1f%%", value))

    data = lift(bmax.value, frequency.value, exponent.value, kh.value, ke.value, noise.value) do b, f, n, hyst, eddy, sigma
        loss_model(b, f, n, hyst, eddy, sigma)
    end
    lines!(loss_axis, lift(value -> value.f, data), lift(value -> value.hysteresis_power, data), color = PINK, linewidth = 2.4, label = "Pₕ")
    lines!(loss_axis, lift(value -> value.f, data), lift(value -> value.eddy_power, data), color = CYAN, linewidth = 2.4, label = "Pₑ")
    lines!(loss_axis, lift(value -> value.f, data), lift(value -> value.observed, data), color = GREEN, linewidth = 2.6, label = "观测总损耗")
    scatter!(loss_axis, lift(value -> [value.f[value.current_index]], data), lift(value -> [value.observed[value.current_index]], data), color = AMBER, markersize = 18)
    axislegend(loss_axis, position = :lt, framevisible = false)
    b_series = collect(range(0.2, 1.4; length = 80))
    lines!(steinmetz_axis, log.(b_series), lift(value -> log.(80.0 .* b_series .^ value.n), data), color = VIOLET, linewidth = 2.8)
    scatter!(steinmetz_axis, lift(value -> [log(value.b)], data), lift(value -> [log(80.0 * value.b^value.n)], data), color = AMBER, markersize = 18)

    values = (
        lift(value -> @sprintf("P总 = %.1f W/m³", value.observed[value.current_index]), data),
        lift(value -> @sprintf("W周期 = %.2f J/m³", value.loop_energy), data),
        lift(value -> @sprintf("n = %.2f", value.n), data),
        lift(value -> @sprintf("uᵣ = %.2f%%", value.uncertainty), data),
    )
    detail = lift(data) do value
        @sprintf("准静态磁滞损耗满足 Wₕ≈kₕBₘⁿ，功率项 Pₕ=fWₕ；涡流项近似 Pₑ∝f²Bₘ²。实验应由 B-H 回线面积直接求每周期损耗，并报告电压、电流、频率、截面积和积分器校准的不确定度。")
    end
    add_metrics!(metrics, values, detail)
    bind_playback!(controls, 7, frequency, 5:5:200, [(bmax, 1.00), (frequency, 50), (exponent, 1.60), (kh, 80), (ke, 0.10), (noise, 1.0)])
    return figure
end

function run_self_test()
    loop = loop_curve(1000.0, 120.0, 0.60, 1.20)
    @assert length(loop.h) == 361
    @assert loop.area > 0
    apparatus = apparatus_model(300, 150, 100, 4.0, 3.0, 90)
    @assert isapprox(maximum(abs, apparatus.h), 50.0; rtol = 1.0e-10)
    demag = demagnetization_model(1200, 0.75, 8, 100, 1.16)
    @assert demag.amplitude < demag.amplitudes[1]
    loss = loss_model(1.0, 50, 1.6, 80, 0.1, 1.0)
    @assert all(loss.total .> 0)
    println("magnetic-hysteresis-self-test:ok")
end

const PAGE_STYLE = """
html, body, .hysteresis-lab { width: $(FIGURE_WIDTH)px; height: $(FIGURE_HEIGHT)px; margin: 0; padding: 0; box-sizing: border-box; overflow: hidden; background: #0b0f14; transform-origin: 0 0; }
.hysteresis-diagnostic { position: fixed; left: 16px; right: 16px; bottom: 16px; z-index: 1002; display: none; padding: 10px 12px; color: #f7d7d7; background: rgba(64,20,28,.94); border: 1px solid rgba(255,85,105,.65); border-radius: 6px; font: 13px/1.5 ui-monospace,Consolas,monospace; white-space: pre-wrap; }
.hysteresis-diagnostic.visible { display: block; }
"""

const CLIENT_STATUS_SCRIPT = """
(() => {
    let ready = false;
    const parentWindow = window.parent || window;
    const send = (type, detail = "") => parentWindow.postMessage({ type, detail }, "*");
    let fitFrame = 0;
    let layoutScale = 1;
    const fitLayout = () => {
        const page = document.querySelector(".hysteresis-lab");
        if (!page) return;
        const viewport = window.visualViewport;
        const width = Math.max(1, viewport ? viewport.width : (document.documentElement.clientWidth || window.innerWidth));
        const height = Math.max(1, viewport ? viewport.height : (document.documentElement.clientHeight || window.innerHeight));
        const scale = Math.min(1.05, (width - 12) / $(FIGURE_WIDTH), (height - 8) / $(FIGURE_HEIGHT));
        layoutScale = scale;
        const left = (viewport ? viewport.offsetLeft : 0) + Math.max(0, (width - $(FIGURE_WIDTH) * scale) / 2);
        const top = (viewport ? viewport.offsetTop : 0) + Math.max(0, (height - $(FIGURE_HEIGHT) * scale) / 2);
        page.style.transform = "translate3d(" + left + "px," + top + "px,0) scale(" + scale + ")";
    };
    const scheduleFit = () => { if (fitFrame) cancelAnimationFrame(fitFrame); fitFrame = requestAnimationFrame(() => { fitFrame = 0; fitLayout(); }); };
    fitLayout(); requestAnimationFrame(fitLayout); window.addEventListener("resize", scheduleFit);
    if (window.visualViewport) window.visualViewport.addEventListener("resize", scheduleFit);
    const syncPointer = event => {
        const canvas = event && event.target instanceof HTMLCanvasElement ? event.target : null;
        const screen = canvas && canvas.wglmakie_screen;
        if (!screen || !Number.isFinite(screen.winscale) || screen.winscale <= 0) return;
        if (!Number.isFinite(screen.__physicsBaseWinscale)) screen.__physicsBaseWinscale = screen.winscale;
        const base = screen.__physicsBaseWinscale;
        screen.winscale = base * layoutScale;
        window.clearTimeout(screen.__physicsPointerScaleTimer);
        screen.__physicsPointerScaleTimer = window.setTimeout(() => { if (canvas.wglmakie_screen === screen) screen.winscale = base; }, 120);
    };
    for (const name of ["mousemove","mousedown","mouseup","pointerdown","pointermove","pointerup","wheel"]) document.addEventListener(name, syncPointer, {capture:true,passive:true});
    const showDiagnostic = detail => {
        let box = document.getElementById("hysteresis-diagnostic");
        if (!box) { box = document.createElement("div"); box.id = "hysteresis-diagnostic"; box.className = "hysteresis-diagnostic"; document.body.appendChild(box); }
        box.textContent = detail; box.classList.add("visible"); send("magnetic-hysteresis-wgl-failed", detail);
    };
    const probe = document.createElement("canvas");
    const gl = probe.getContext("webgl2") ? "webgl2" : (probe.getContext("webgl") ? "webgl1" : "none");
    if (gl === "none") { showDiagnostic("浏览器无法创建 WebGL 上下文"); return; }
    const startedAt = performance.now();
    const check = () => {
        const canvas = document.querySelector("canvas");
        const spinner = document.querySelector(".wglmakie-spinner");
        const spinnerVisible = Boolean(spinner && spinner.getClientRects().length > 0 && getComputedStyle(spinner).visibility !== "hidden");
        if (canvas && canvas.width > 0 && canvas.height > 0 && !spinnerVisible) { ready = true; send("magnetic-hysteresis-wgl-ready", gl); return; }
        if (!ready && performance.now() - startedAt > 75000) { showDiagnostic("WGLMakie/Bonito 初始化超过 75 秒"); return; }
        window.setTimeout(check, 300);
    };
    window.addEventListener("error", event => showDiagnostic("浏览器脚本错误：" + event.message));
    window.addEventListener("unhandledrejection", event => showDiagnostic("浏览器 Promise 错误：" + String(event.reason)));
    check();
})();
"""

function experiment_app(title, builder)
    return Bonito.App(; title = title) do
        figure = builder()
        DOM.div(DOM.style(PAGE_STYLE), DOM.div(figure; class = "hysteresis-lab"), DOM.script(CLIENT_STATUS_SCRIPT))
    end
end

function index_app()
    links = [
        DOM.a(name; href = path, style = "color:#73d7cf;margin-right:24px")
        for (name, path) in (
            ("基本磁滞回线与特征量", "./loop"),
            ("示波器法与积分器标定", "./apparatus"),
            ("交流退磁与剩磁衰减", "./demagnetization"),
            ("损耗分离与不确定度", "./fit"),
        )
    ]
    return Bonito.App(DOM.div(DOM.style(PAGE_STYLE), DOM.h1("铁磁滞回线测定与观察"), DOM.div(links...), style = "padding:32px;background:#0b0f14;color:#eef3f8;min-height:100vh"); title = "铁磁滞回线测定与观察")
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
    host = get(ENV, "MAGNETIC_HYSTERESIS_WEB_HOST", "127.0.0.1")
    port = parse(Int, get(ENV, "MAGNETIC_HYSTERESIS_WEB_PORT", "9398"))
    proxy_url = strip(get(ENV, "MAGNETIC_HYSTERESIS_WEB_PROXY_URL", "."))
    isempty(proxy_url) && (proxy_url = ".")
    server = Bonito.Server(host, port; proxy_url = proxy_url)
    Bonito.route!(server, "/__physics_health__" => health_app())
    Bonito.route!(server, "/" => index_app())
    Bonito.route!(server, "/loop" => experiment_app("基本磁滞回线与特征量", loop_figure))
    Bonito.route!(server, "/apparatus" => experiment_app("示波器法与积分器标定", apparatus_figure))
    Bonito.route!(server, "/demagnetization" => experiment_app("交流退磁与剩磁衰减", demagnetization_figure))
    Bonito.route!(server, "/fit" => experiment_app("损耗分离与不确定度", fit_figure))
    println("铁磁滞回线网页实验已启动：http://$(host):$(port)")
    wait(server)
end

if abspath(PROGRAM_FILE) == @__FILE__
    main()
end
