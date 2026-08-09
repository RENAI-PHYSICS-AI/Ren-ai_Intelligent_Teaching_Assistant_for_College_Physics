const LAB_DIR = @__DIR__
if abspath(PROGRAM_FILE) == @__FILE__
    import Pkg
    Pkg.activate(LAB_DIR)
    if !("--no-instantiate" in ARGS)
        Pkg.instantiate()
    end
end

using Dates
import Bonito
using Printf
using Random
using WGLMakie

const DOM = Bonito.DOM
const Slider = WGLMakie.Makie.Slider
const Button = WGLMakie.Makie.Button

const TWO_PI = 2pi
const CYAN = RGBf(0.18, 0.78, 0.92)
const PINK = RGBf(0.94, 0.35, 0.50)
const AMBER = RGBf(1.00, 0.72, 0.24)
const GREEN = RGBf(0.36, 0.82, 0.55)
const MUTED = RGBf(0.58, 0.62, 0.70)
const PANEL_BG = RGBf(0.075, 0.085, 0.105)
const BUTTON_BG = RGBf(0.13, 0.15, 0.19)
const BUTTON_ACTIVE = RGBf(0.15, 0.42, 0.58)
const CJK_PROBE_TEXT = "中文相位差实验"
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

const MODE_ORDER = (:echo, :dual, :phase, :standing)
const MODE_NAMES = Dict(
    :echo => "回声法",
    :dual => "双麦克风时间差法",
    :phase => "示波器相位差法",
    :standing => "驻波法",
)
const MODE_FILES = Dict(
    :echo => "echo",
    :dual => "dual_microphone",
    :phase => "oscilloscope_phase",
    :standing => "standing_wave",
)

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

function load_packaged_wgl_shaders!()
    asset_dir = normpath(
        joinpath(Sys.BINDIR, "..", "share", "sound_speed", "wglmakie_assets"),
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
            "sound_speed",
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
        "未找到真正包含中文字形的字体。请重新执行 install.sh，或通过 PHYSICS_CJK_FONT 指定 Noto Sans CJK SC 字体文件。",
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
        "/usr/share/fonts/google-noto-cjk-fonts/NotoSansCJK-Bold.ttc",
        fontconfig_match("Noto Sans CJK SC Bold:lang=zh-cn"),
    ])
    isnothing(bold) && (bold = regular)
    return (; regular, bold)
end

gaussian(time, center, width) = @. exp(-0.5 * ((time - center) / width)^2)
noise_scale(snr_db) = 10.0^(-snr_db / 20.0)

function peak_time(signal, time, center, half_width)
    indices = findall(value -> abs(value - center) <= half_width, time)
    isempty(indices) && return center
    local_index = argmax(abs.(signal[indices]))
    return time[indices[local_index]]
end

function echo_model(speed, distance, sample_rate, snr, reflection)
    delay = 2distance / speed
    pulse_time = 0.002
    width = 0.00028
    duration = pulse_time + delay + 0.004
    time = collect(0.0:inv(sample_rate):duration)
    count = length(time)
    direct = gaussian(time, pulse_time, width)
    echo = reflection .* gaussian(time, pulse_time + delay, width)
    rng = MersenneTwister(20260730)
    measured = direct .+ echo .+ noise_scale(snr) .* randn(rng, count)
    first_peak = peak_time(measured, time, pulse_time, 3width)
    second_peak = peak_time(measured, time, pulse_time + delay, 3width)
    measured_delay = max(second_peak - first_peak, eps())
    estimate = 2distance / measured_delay
    delays = collect(range(0.0, max(1.2delay, 0.01); length = 300))
    return (;
        time,
        direct,
        echo,
        measured,
        delay,
        measured_delay,
        estimate,
        pulse_time,
        distance,
        analysis_x = 1000 .* delays,
        analysis_y = speed .* delays,
    )
end

function lag_correlation(x, y, max_lag)
    lags = collect(-max_lag:max_lag)
    correlation = zeros(Float64, length(lags))
    for (index, lag) in pairs(lags)
        if lag >= 0
            xa = @view x[1:(end - lag)]
            ya = @view y[(1 + lag):end]
        else
            xa = @view x[(1 - lag):end]
            ya = @view y[1:(end + lag)]
        end
        denominator = sqrt(sum(abs2, xa) * sum(abs2, ya))
        correlation[index] = denominator > 0 ? sum(xa .* ya) / denominator : 0.0
    end
    return lags, correlation
end

function dual_microphone_model(speed, distance, angle_degree, sample_rate, snr)
    projected_distance = distance * cosd(angle_degree)
    delay = projected_distance / speed
    pulse_time = 0.003
    width = 0.00035
    duration = pulse_time + delay + 0.005
    time = collect(0.0:inv(sample_rate):duration)
    count = length(time)
    rng = MersenneTwister(20260731)
    sigma = noise_scale(snr)
    channel_1 = gaussian(time, pulse_time, width) .+ sigma .* randn(rng, count)
    channel_2 = gaussian(time, pulse_time + delay, width) .+ sigma .* randn(rng, count)
    max_lag = min(count - 10, ceil(Int, (delay + 0.003) * sample_rate))
    lags, correlation = lag_correlation(channel_1, channel_2, max_lag)
    best_lag = lags[argmax(correlation)]
    measured_delay = max(best_lag / sample_rate, eps())
    estimate = projected_distance / measured_delay
    return (;
        time,
        channel_1,
        channel_2,
        delay,
        measured_delay,
        estimate,
        projected_distance,
        pulse_time,
        distance,
        angle_degree,
        lags,
        lag_ms = 1000 .* lags ./ sample_rate,
        correlation,
        best_lag,
    )
end

function phase_model(speed, distance, frequency, snr, cycle_count)
    total_phase = TWO_PI * frequency * distance / speed
    true_cycles = floor(Int, total_phase / TWO_PI)
    wrapped_phase = mod(total_phase, TWO_PI)
    period = inv(frequency)
    time = collect(range(0.0, 2period; length = 1200))
    rng = MersenneTwister(20260801)
    sigma = noise_scale(snr)
    channel_1 = sin.(TWO_PI .* frequency .* time) .+ sigma .* randn(rng, length(time))
    channel_2 =
        sin.(TWO_PI .* frequency .* time .- total_phase) .+
        sigma .* randn(rng, length(time))
    projection_1 = sum(channel_1 .* cis.(-TWO_PI .* frequency .* time))
    projection_2 = sum(channel_2 .* cis.(-TWO_PI .* frequency .* time))
    measured_wrapped = mod(-angle(projection_2 / projection_1), TWO_PI)
    reconstructed_phase = TWO_PI * cycle_count + measured_wrapped
    estimate = reconstructed_phase > 1.0e-12 ?
        TWO_PI * frequency * distance / reconstructed_phase : Inf
    distance_grid = collect(range(0.0, max(1.2distance, 1.0); length = 700))
    phase_grid = mod.(TWO_PI .* frequency .* distance_grid ./ speed, TWO_PI)
    return (;
        time,
        channel_1,
        channel_2,
        total_phase,
        wrapped_phase,
        measured_wrapped,
        true_cycles,
        cycle_count,
        estimate,
        distance,
        frequency,
        distance_grid,
        phase_degree_grid = rad2deg.(phase_grid),
    )
end

function standing_wave_model(speed, tube_length, frequency, reflection, node_spans, progress)
    wavelength = speed / frequency
    wave_number = TWO_PI / wavelength
    omega = TWO_PI * frequency
    time = progress / frequency
    count = 1400
    x = collect(range(0.0, tube_length; length = count))
    incident = sin.(wave_number .* x .- omega * time)
    reflected = reflection .* sin.(wave_number .* x .+ omega * time)
    resultant = incident .+ reflected
    envelope_upper = sqrt.(
        1 .+ reflection^2 .- 2reflection .* cos.(2wave_number .* x),
    )
    node_spacing = wavelength / 2
    measured_span = node_spans * node_spacing
    estimate = 2frequency * measured_span / node_spans
    nodes = collect(0.0:node_spacing:tube_length)
    return (;
        x,
        incident,
        reflected,
        resultant,
        envelope_upper,
        envelope_lower = -envelope_upper,
        wavelength,
        node_spacing,
        measured_span,
        estimate,
        nodes,
        time,
        tube_length,
        frequency,
        reflection,
        node_spans,
    )
end

function set_block_visible!(block, visible)
    block.blockscene.visible[] = visible
    return nothing
end

function set_axis_visible!(axis, visible)
    axis.blockscene.visible[] = visible
    axis.scene.visible[] = visible
    return nothing
end

function line_segments(xs, low, high)
    points = Point2f[]
    for x in xs
        push!(points, Point2f(x, low), Point2f(x, high))
    end
    return points
end

function write_csv(path, mode, parameters, data)
    open(path, "w") do io
        println(io, "# 声速四种方法综合可视化实验")
        println(io, "# method=$(MODE_NAMES[mode])")
        println(io, "# true_speed_m_s=$(parameters.speed)")
        println(io, "# estimated_speed_m_s=$(data.estimate)")
        if mode == :echo
            println(io, "# theoretical_delay_s=$(data.delay)")
            println(io, "# measured_delay_s=$(data.measured_delay)")
            println(io, "time_s,direct,echo,measured")
            for index in eachindex(data.time)
                println(
                    io,
                    "$(data.time[index]),$(data.direct[index])," *
                    "$(data.echo[index]),$(data.measured[index])",
                )
            end
        elseif mode == :dual
            println(io, "# theoretical_delay_s=$(data.delay)")
            println(io, "# measured_delay_s=$(data.measured_delay)")
            println(io, "# projected_distance_m=$(data.projected_distance)")
            println(io, "time_s,microphone_1,microphone_2")
            for index in eachindex(data.time)
                println(io, "$(data.time[index]),$(data.channel_1[index]),$(data.channel_2[index])")
            end
            println(io, "# lag_ms,normalized_correlation")
            for index in eachindex(data.lag_ms)
                println(io, "# $(data.lag_ms[index]),$(data.correlation[index])")
            end
        elseif mode == :phase
            println(io, "# measured_wrapped_phase_rad=$(data.measured_wrapped)")
            println(io, "# assumed_cycle_count=$(data.cycle_count)")
            println(io, "time_s,channel_1,channel_2")
            for index in eachindex(data.time)
                println(io, "$(data.time[index]),$(data.channel_1[index]),$(data.channel_2[index])")
            end
        else
            println(io, "# wavelength_m=$(data.wavelength)")
            println(io, "# adjacent_node_spacing_m=$(data.node_spacing)")
            println(io, "position_m,incident,reflected,resultant,envelope")
            for index in eachindex(data.x)
                println(
                    io,
                    "$(data.x[index]),$(data.incident[index]),$(data.reflected[index])," *
                    "$(data.resultant[index]),$(data.envelope_upper[index])",
                )
            end
        end
    end
end

function build_lab()
    fonts = cjk_font_family()
    set_theme!(
        Theme(
            fontsize = 15,
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
            ),
        ),
    )

    figure = Figure(size = (1000, 800), figure_padding = 24)
    Label(
        figure[2, 1:3],
        "同一真实声速 · 四种观测量 · 对比测量误差与适用条件",
        color = MUTED,
        halign = :left,
    )

    mode = Observable(:echo)
    mode_bar = GridLayout()
    figure[3, 1:3] = mode_bar
    mode_buttons = Dict{Symbol, Button}()
    for (column, key) in enumerate(MODE_ORDER)
        button = Button(
            mode_bar[1, column],
            label = MODE_NAMES[key],
            height = 34,
            buttoncolor = key == :echo ? BUTTON_ACTIVE : BUTTON_BG,
            labelcolor = :white,
        )
        mode_buttons[key] = button
    end

    space_title = Observable("空间传播：声源 → 墙面 → 声源")
    middle_title = Observable("接收波形：直达脉冲与回声脉冲")
    middle_xlabel = Observable("时间 / ms")
    space_axis = Axis(figure[4, 1], title = space_title, xlabel = "位置 / m", ylabel = "归一化幅度")
    middle_axis = Axis(figure[4, 2], title = middle_title, xlabel = middle_xlabel, ylabel = "信号")

    echo_axis = Axis(figure[4, 3], title = "路程—时间关系（斜率为声速）", xlabel = "往返时间 / ms", ylabel = "路程 2d / m")
    dual_axis = Axis(figure[4, 3], title = "互相关峰值定位时间差", xlabel = "时延 / ms", ylabel = "归一化相关")
    phase_axis = Axis(figure[4, 3], title = "相位周期性与整数周歧义", xlabel = "麦克风间距 / m", ylabel = "相位 / °")
    standing_axis = Axis(figure[4, 3], title = "驻波包络与波节位置", xlabel = "位置 / m", ylabel = "包络")
    analysis_axes = Dict(
        :echo => echo_axis,
        :dual => dual_axis,
        :phase => phase_axis,
        :standing => standing_axis,
    )

    space_curve1 = Observable(Point2f[])
    space_curve2 = Observable(Point2f[])
    space_curve3 = Observable(Point2f[])
    space_points = Observable(Point2f[])
    space_guides = Observable(Point2f[])
    middle_curve1 = Observable(Point2f[])
    middle_curve2 = Observable(Point2f[])
    middle_curve3 = Observable(Point2f[])
    middle_reference1 = Observable(Point2f[])
    middle_reference2 = Observable(Point2f[])
    middle_reference3 = Observable(Point2f[])
    middle_points = Observable(Point2f[])
    middle_guides = Observable(Point2f[])

    lines!(space_axis, space_curve1, color = CYAN, linewidth = 2.4)
    lines!(space_axis, space_curve2, color = PINK, linewidth = 2.0)
    lines!(space_axis, space_curve3, color = AMBER, linewidth = 3.0)
    scatter!(space_axis, space_points, color = GREEN, markersize = 16, strokecolor = :white, strokewidth = 1)
    linesegments!(space_axis, space_guides, color = (:white, 0.40), linewidth = 1.5, linestyle = :dash)
    hlines!(space_axis, [0.0], color = (:white, 0.12))

    lines!(middle_axis, middle_reference1, color = (CYAN, 0.20), linewidth = 1.3)
    lines!(middle_axis, middle_reference2, color = (PINK, 0.20), linewidth = 1.3)
    lines!(middle_axis, middle_reference3, color = (AMBER, 0.18), linewidth = 1.3)
    lines!(middle_axis, middle_curve1, color = CYAN, linewidth = 2.2)
    lines!(middle_axis, middle_curve2, color = PINK, linewidth = 2.2)
    lines!(middle_axis, middle_curve3, color = AMBER, linewidth = 2.7)
    scatter!(middle_axis, middle_points, color = :white, markersize = 8)
    linesegments!(middle_axis, middle_guides, color = (:white, 0.42), linewidth = 1.4, linestyle = :dash)
    hlines!(middle_axis, [0.0], color = (:white, 0.12))

    echo_reference = Observable(Point2f[])
    echo_curve = Observable(Point2f[])
    echo_point = Observable(Point2f[])
    lines!(echo_axis, echo_reference, color = (CYAN, 0.25), linewidth = 1.5)
    lines!(echo_axis, echo_curve, color = CYAN, linewidth = 2.8)
    scatter!(echo_axis, echo_point, color = AMBER, markersize = 14)

    dual_reference = Observable(Point2f[])
    dual_curve = Observable(Point2f[])
    dual_point = Observable(Point2f[])
    lines!(dual_axis, dual_reference, color = (CYAN, 0.24), linewidth = 1.5)
    lines!(dual_axis, dual_curve, color = CYAN, linewidth = 2.6)
    scatter!(dual_axis, dual_point, color = AMBER, markersize = 14)
    vlines!(dual_axis, [0.0], color = (:white, 0.15))

    phase_reference = Observable(Point2f[])
    phase_curve = Observable(Point2f[])
    phase_point = Observable(Point2f[])
    lines!(phase_axis, phase_reference, color = (CYAN, 0.24), linewidth = 1.5)
    lines!(phase_axis, phase_curve, color = CYAN, linewidth = 2.5)
    scatter!(phase_axis, phase_point, color = AMBER, markersize = 14)

    standing_x = Observable(Float64[])
    standing_upper = Observable(Float64[])
    standing_lower = Observable(Float64[])
    standing_nodes = Observable(Point2f[])
    lines!(standing_axis, standing_x, standing_upper, color = GREEN, linewidth = 2.3)
    lines!(standing_axis, standing_x, standing_lower, color = GREEN, linewidth = 2.3)
    scatter!(standing_axis, standing_nodes, color = AMBER, markersize = 9)

    controls = GridLayout()
    figure[5, 1:3] = controls
    basic = GridLayout()
    special = GridLayout()
    motion = GridLayout()
    controls[1, 1] = basic
    controls[1, 2] = special
    controls[1, 3] = motion

    speed_slider = Slider(basic[1, 2], range = 300:1:380, startvalue = 343, update_while_dragging = false)
    distance_slider = Slider(basic[2, 2], range = 0.2:0.1:8.0, startvalue = 3.0, update_while_dragging = false)
    frequency_slider = Slider(basic[3, 2], range = 100:10:2000, startvalue = 500, update_while_dragging = false)
    snr_slider = Slider(basic[4, 2], range = 5:1:60, startvalue = 30, update_while_dragging = false)
    speed_label = Label(basic[1, 1], "真实声速 v", halign = :right)
    distance_label_text = Observable("墙面距离 d")
    distance_label = Label(basic[2, 1], distance_label_text, halign = :right)
    frequency_label = Label(basic[3, 1], "频率 f", halign = :right)
    snr_label = Label(basic[4, 1], "信噪比 SNR", halign = :right)
    speed_value = Label(basic[1, 3], lift(v -> @sprintf("%.0f m/s", v), speed_slider.value))
    distance_value = Label(basic[2, 3], lift(v -> @sprintf("%.2f m", v), distance_slider.value))
    frequency_value = Label(basic[3, 3], lift(v -> @sprintf("%.0f Hz", v), frequency_slider.value))
    snr_value = Label(basic[4, 3], lift(v -> @sprintf("%.0f dB", v), snr_slider.value))

    angle_slider = Slider(special[1, 2], range = 0:1:70, startvalue = 0, update_while_dragging = false)
    sample_rate_slider = Slider(special[2, 2], range = [8000, 16000, 24000, 48000], startvalue = 48000, update_while_dragging = false)
    reflection_slider = Slider(special[3, 2], range = 0.2:0.05:1.0, startvalue = 0.75, update_while_dragging = false)
    cycle_slider = Slider(special[4, 2], range = 0:1:20, startvalue = 4, update_while_dragging = false)
    node_span_slider = Slider(special[5, 2], range = 1:1:8, startvalue = 4, update_while_dragging = false)
    angle_label = Label(special[1, 1], "入射夹角 θ", halign = :right)
    sample_rate_label = Label(special[2, 1], "采样率 fs", halign = :right)
    reflection_label = Label(special[3, 1], "反射系数 r", halign = :right)
    cycle_label = Label(special[4, 1], "假设完整周期 n", halign = :right)
    node_span_label = Label(special[5, 1], "测量波节间隔数 q", halign = :right)
    angle_value = Label(special[1, 3], lift(v -> @sprintf("%.0f°", v), angle_slider.value))
    sample_rate_value = Label(special[2, 3], lift(v -> @sprintf("%.0f Hz", v), sample_rate_slider.value))
    reflection_value = Label(special[3, 3], lift(v -> @sprintf("%.2f", v), reflection_slider.value))
    cycle_value = Label(special[4, 3], lift(string, cycle_slider.value))
    node_span_value = Label(special[5, 3], lift(string, node_span_slider.value))

    progress_slider = Slider(motion[1, 2], range = 0:1:1000, startvalue = 250, update_while_dragging = true)
    playback_slider = Slider(motion[2, 2], range = 0.25:0.25:2.0, startvalue = 0.5, update_while_dragging = true)
    Label(motion[1, 1], "传播/振动进程", halign = :right)
    Label(motion[2, 1], "播放速度", halign = :right)
    Label(motion[1, 3], lift(v -> @sprintf("%.1f%%", v / 10), progress_slider.value))
    Label(motion[2, 3], lift(v -> @sprintf("%.2f×", v), playback_slider.value))

    playing = Observable(false)
    play_button = Button(motion[3, 1], label = lift(v -> v ? "暂停" : "播放", playing), height = 30, buttoncolor = BUTTON_BG)
    reset_button = Button(motion[3, 2], label = "重置", height = 30, buttoncolor = BUTTON_BG)
    export_button = Button(motion[4, 1:2], label = "导出 CSV", height = 30, buttoncolor = BUTTON_BG)
    status = Observable("就绪")
    status_color = lift(text -> startswith(text, "正在") ? AMBER : GREEN, status)
    Label(motion[5, 1:3], status, color = status_color, halign = :left, font = :bold)

    analysis = GridLayout()
    figure[6, 1:3] = analysis
    metric_1 = Observable("")
    metric_2 = Observable("")
    metric_3 = Observable("")
    metric_4 = Observable("")
    detail = Observable("")
    Label(analysis[1, 1:4], "实时测量结果", font = :bold, halign = :left)
    Label(analysis[2, 1], metric_1, halign = :left)
    Label(analysis[2, 2], metric_2, halign = :left)
    Label(analysis[2, 3], metric_3, halign = :left)
    Label(analysis[2, 4], metric_4, halign = :left)
    Label(analysis[3, 1:4], detail, halign = :left, color = MUTED)

    current_data = Ref{Any}()
    current_parameters = Ref{Any}()

    function parameters()
        return (
            speed = Float64(speed_slider.value[]),
            distance = Float64(distance_slider.value[]),
            frequency = Float64(frequency_slider.value[]),
            snr = Float64(snr_slider.value[]),
            angle = Float64(angle_slider.value[]),
            sample_rate = Float64(sample_rate_slider.value[]),
            reflection = Float64(reflection_slider.value[]),
            cycles = Int(cycle_slider.value[]),
            node_spans = Int(node_span_slider.value[]),
        )
    end

    function update_visibility()
        active = mode[]
        for (key, axis) in analysis_axes
            set_axis_visible!(axis, key == active)
        end
        show_frequency = active in (:phase, :standing)
        show_snr = active in (:echo, :dual, :phase)
        show_angle = active == :dual
        show_sample_rate = active in (:echo, :dual)
        show_reflection = active in (:echo, :standing)
        show_cycles = active == :phase
        show_node_span = active == :standing
        for block in (frequency_label, frequency_slider, frequency_value)
            set_block_visible!(block, show_frequency)
        end
        for block in (snr_label, snr_slider, snr_value)
            set_block_visible!(block, show_snr)
        end
        for (blocks, visible) in (
            ((angle_label, angle_slider, angle_value), show_angle),
            ((sample_rate_label, sample_rate_slider, sample_rate_value), show_sample_rate),
            ((reflection_label, reflection_slider, reflection_value), show_reflection),
            ((cycle_label, cycle_slider, cycle_value), show_cycles),
            ((node_span_label, node_span_slider, node_span_value), show_node_span),
        )
            for block in blocks
                set_block_visible!(block, visible)
            end
        end
        distance_label_text[] = active == :echo ? "墙面距离 d" :
            active in (:dual, :phase) ? "麦克风间距 d" : "驻波管长度 L"
        for (key, button) in mode_buttons
            button.buttoncolor[] = key == active ? BUTTON_ACTIVE : BUTTON_BG
        end
        return nothing
    end

    function clear_series()
        space_curve1[] = Point2f[]
        space_curve2[] = Point2f[]
        space_curve3[] = Point2f[]
        space_points[] = Point2f[]
        space_guides[] = Point2f[]
        middle_curve1[] = Point2f[]
        middle_curve2[] = Point2f[]
        middle_curve3[] = Point2f[]
        middle_points[] = Point2f[]
        middle_guides[] = Point2f[]
    end

    function update_frame(progress_integer)
        p = current_parameters[]
        data = current_data[]
        progress = progress_integer / 1000
        active = mode[]
        clear_series()

        if active == :echo
            path_progress = 2progress
            front = path_progress <= 1 ? path_progress * p.distance : (2 - path_progress) * p.distance
            sample_index = clamp(
                floor(Int, progress * (length(data.time) - 1)) + 1,
                1,
                length(data.time),
            )
            time_ms = 1000 .* data.time
            space_curve1[] = Point2f.(Float32[0.0, p.distance], 0.0)
            space_points[] = Point2f[Point2f(0, 0), Point2f(p.distance, 0), Point2f(front, 0)]
            space_guides[] = line_segments([p.distance], -0.8, 0.8)
            middle_curve1[] = Point2f.(time_ms[1:sample_index], data.direct[1:sample_index])
            middle_curve2[] = Point2f.(time_ms[1:sample_index], data.echo[1:sample_index])
            middle_curve3[] = Point2f.(time_ms[1:sample_index], data.measured[1:sample_index])
            middle_points[] = Point2f[
                Point2f(time_ms[sample_index], data.measured[sample_index]),
            ]
            middle_guides[] = line_segments(
                [time_ms[sample_index]],
                -0.5,
                1.25,
            )
            current_delay_ms = 1000 * progress * data.measured_delay
            current_path = progress * 2p.distance
            echo_curve[] = Point2f[
                Point2f(0, 0),
                Point2f(current_delay_ms, current_path),
            ]
            echo_point[] = Point2f[Point2f(current_delay_ms, current_path)]
            limits!(space_axis, -0.1, 1.08p.distance, -1.0, 1.0)
            limits!(middle_axis, 0.0, 1000last(data.time), -0.55, 1.35)
        elseif active == :dual
            front = -0.3p.distance + progress * 1.8p.distance
            sample_index = clamp(
                floor(Int, progress * (length(data.time) - 1)) + 1,
                1,
                length(data.time),
            )
            correlation_index = clamp(
                floor(Int, progress * (length(data.lag_ms) - 1)) + 1,
                1,
                length(data.lag_ms),
            )
            time_ms = 1000 .* data.time
            space_curve1[] = Point2f.(Float32[-0.3p.distance, 1.3p.distance], 0.0)
            space_points[] = Point2f[Point2f(0, 0), Point2f(p.distance, 0), Point2f(front, 0)]
            space_guides[] = line_segments([front], -0.8, 0.8)
            middle_curve1[] = Point2f.(
                time_ms[1:sample_index],
                data.channel_1[1:sample_index],
            )
            middle_curve2[] = Point2f.(
                time_ms[1:sample_index],
                data.channel_2[1:sample_index],
            )
            middle_points[] = Point2f[
                Point2f(time_ms[sample_index], data.channel_1[sample_index]),
                Point2f(time_ms[sample_index], data.channel_2[sample_index]),
            ]
            middle_guides[] = line_segments(
                [time_ms[sample_index]],
                -0.6,
                1.3,
            )
            dual_curve[] = Point2f.(
                data.lag_ms[1:correlation_index],
                data.correlation[1:correlation_index],
            )
            if progress >= 0.999
                peak_index = argmax(data.correlation)
                dual_point[] = Point2f[
                    Point2f(data.lag_ms[peak_index], data.correlation[peak_index]),
                ]
            else
                dual_point[] = Point2f[
                    Point2f(
                        data.lag_ms[correlation_index],
                        data.correlation[correlation_index],
                    ),
                ]
            end
            limits!(space_axis, -0.35p.distance, 1.35p.distance, -1.0, 1.0)
            limits!(middle_axis, 0.0, 1000last(data.time), -0.65, 1.4)
        elseif active == :phase
            wavelength = p.speed / p.frequency
            x = collect(range(0.0, max(1.15p.distance, wavelength); length = 1000))
            sample_index = clamp(
                floor(Int, progress * (length(data.time) - 1)) + 1,
                1,
                length(data.time),
            )
            current_distance = progress * p.distance
            phase_index = something(
                findlast(value -> value <= current_distance, data.distance_grid),
                1,
            )
            time_ms = 1000 .* data.time
            space_curve1[] = Point2f.(
                x,
                sin.(TWO_PI .* x ./ wavelength .- TWO_PI * progress),
            )
            space_points[] = Point2f[Point2f(0, 0), Point2f(p.distance, 0)]
            space_guides[] = line_segments([0.0, p.distance], -1.1, 1.1)
            middle_curve1[] = Point2f.(
                time_ms[1:sample_index],
                data.channel_1[1:sample_index],
            )
            middle_curve2[] = Point2f.(
                time_ms[1:sample_index],
                data.channel_2[1:sample_index],
            )
            middle_points[] = Point2f[
                Point2f(time_ms[sample_index], data.channel_1[sample_index]),
                Point2f(time_ms[sample_index], data.channel_2[sample_index]),
            ]
            middle_guides[] = line_segments(
                [time_ms[sample_index]],
                -1.25,
                1.25,
            )
            phase_curve[] = Point2f.(
                data.distance_grid[1:phase_index],
                data.phase_degree_grid[1:phase_index],
            )
            current_phase = mod(
                TWO_PI * p.frequency * current_distance / p.speed,
                TWO_PI,
            )
            phase_point[] = Point2f[
                Point2f(current_distance, rad2deg(current_phase)),
            ]
            limits!(space_axis, 0.0, last(x), -1.2, 1.2)
            limits!(middle_axis, 0.0, 1000last(data.time), -1.35, 1.35)
        else
            fresh = standing_wave_model(
                p.speed,
                p.distance,
                p.frequency,
                p.reflection,
                p.node_spans,
                progress,
            )
            current_data[] = fresh
            data = fresh
            space_curve3[] = Point2f.(data.x, data.resultant)
            space_points[] = Point2f.(data.nodes, 0.0)
            middle_curve1[] = Point2f.(data.x, data.incident)
            middle_curve2[] = Point2f.(data.x, data.reflected)
            middle_curve3[] = Point2f.(data.x, data.resultant)
            limits!(space_axis, 0.0, p.distance, -2.2, 2.2)
            limits!(middle_axis, 0.0, p.distance, -2.2, 2.2)
        end
        return nothing
    end

    function recompute()
        status[] = "正在计算..."
        yield()
        p = parameters()
        current_parameters[] = p
        active = mode[]
        if active == :echo
            data = echo_model(p.speed, p.distance, p.sample_rate, p.snr, p.reflection)
            middle_reference1[] = Point2f.(1000 .* data.time, data.direct)
            middle_reference2[] = Point2f.(1000 .* data.time, data.echo)
            middle_reference3[] = Point2f.(1000 .* data.time, data.measured)
            echo_reference[] = Point2f.(data.analysis_x, data.analysis_y)
            limits!(echo_axis, 0.0, maximum(data.analysis_x), 0.0, 1.15maximum(data.analysis_y))
            space_title[] = "空间传播：声源 → 墙面 → 声源"
            middle_title[] = "蓝：直达脉冲　红：回声　黄：含噪测量信号"
            middle_xlabel[] = "时间 / ms"
            error_percent = 100 * (data.estimate - p.speed) / p.speed
            metric_1[] = @sprintf("理论 Δt = %.3f ms", 1000data.delay)
            metric_2[] = @sprintf("测量 Δt = %.3f ms", 1000data.measured_delay)
            metric_3[] = @sprintf("估计 v = %.2f m/s", data.estimate)
            metric_4[] = @sprintf("相对误差 = %+.2f%%", error_percent)
            detail[] = "改变墙面距离、采样率、信噪比与反射系数，观察两个脉冲是否仍能可靠分离。"
        elseif active == :dual
            data = dual_microphone_model(p.speed, p.distance, p.angle, p.sample_rate, p.snr)
            middle_reference1[] = Point2f.(1000 .* data.time, data.channel_1)
            middle_reference2[] = Point2f.(1000 .* data.time, data.channel_2)
            middle_reference3[] = Point2f[]
            dual_reference[] = Point2f.(data.lag_ms, data.correlation)
            limits!(dual_axis, first(data.lag_ms), last(data.lag_ms), -0.3, 1.08)
            space_title[] = "空间传播：两麦克风基线与波前"
            middle_title[] = "蓝：麦克风 1　红：麦克风 2"
            middle_xlabel[] = "时间 / ms"
            error_percent = 100 * (data.estimate - p.speed) / p.speed
            metric_1[] = @sprintf("投影间距 = %.3f m", data.projected_distance)
            metric_2[] = @sprintf("相关峰 Δt = %.3f ms", 1000data.measured_delay)
            metric_3[] = @sprintf("估计 v = %.2f m/s", data.estimate)
            metric_4[] = @sprintf("相对误差 = %+.2f%%", error_percent)
            detail[] = "互相关峰给出整数采样点时延；夹角 θ 通过 d cosθ 改变有效传播距离。"
        elseif active == :phase
            data = phase_model(p.speed, p.distance, p.frequency, p.snr, p.cycles)
            middle_reference1[] = Point2f.(1000 .* data.time, data.channel_1)
            middle_reference2[] = Point2f.(1000 .* data.time, data.channel_2)
            middle_reference3[] = Point2f[]
            phase_reference[] = Point2f.(data.distance_grid, data.phase_degree_grid)
            limits!(phase_axis, 0.0, last(data.distance_grid), 0.0, 370.0)
            space_title[] = "行波与两个麦克风的空间采样"
            middle_title[] = "示波器双通道：水平位移对应相位差"
            middle_xlabel[] = "时间 / ms"
            error_text = isfinite(data.estimate) ?
                @sprintf("%+.2f%%", 100 * (data.estimate - p.speed) / p.speed) : "未定义"
            metric_1[] = @sprintf("包裹相位 = %.1f°", rad2deg(data.measured_wrapped))
            metric_2[] = "真实完整周期 n = $(data.true_cycles)"
            metric_3[] = isfinite(data.estimate) ? @sprintf("估计 v = %.2f m/s", data.estimate) : "估计 v = ∞"
            metric_4[] = "相对误差 = $error_text"
            detail[] = p.cycles == data.true_cycles ?
                "完整周期数选择正确；相位展开后可恢复传播时间。" :
                "当前 n 与真实周期数不同，展示了单次包裹相位测量的多值性。"
        else
            data = standing_wave_model(
                p.speed,
                p.distance,
                p.frequency,
                p.reflection,
                p.node_spans,
                progress_slider.value[] / 1000,
            )
            standing_x[] = data.x
            standing_upper[] = data.envelope_upper
            standing_lower[] = data.envelope_lower
            standing_nodes[] = Point2f.(data.nodes, 0.0)
            middle_reference1[] = Point2f[]
            middle_reference2[] = Point2f[]
            middle_reference3[] = Point2f[]
            limits!(standing_axis, 0.0, p.distance, -2.1, 2.1)
            space_title[] = "驻波瞬时形状与波节位置"
            middle_title[] = "蓝：入射波　红：反射波　黄：叠加驻波"
            middle_xlabel[] = "位置 / m"
            metric_1[] = @sprintf("波长 λ = %.4f m", data.wavelength)
            metric_2[] = @sprintf("相邻波节 = %.4f m", data.node_spacing)
            metric_3[] = @sprintf("%d 个间隔 = %.4f m", p.node_spans, data.measured_span)
            metric_4[] = @sprintf("估计 v = %.2f m/s", data.estimate)
            detail[] = "测量多个波节间隔再取平均可降低读数误差；反射系数降低时，波节不再完全为零。"
        end
        current_data[] = data
        update_frame(progress_slider.value[])
        status[] = "就绪"
        return nothing
    end

    for (key, button) in mode_buttons
        on(button.clicks) do _
            playing[] = false
            mode[] = key
        end
    end
    on(mode) do _
        update_visibility()
        recompute()
    end
    onany(
        speed_slider.value,
        distance_slider.value,
        frequency_slider.value,
        snr_slider.value,
        angle_slider.value,
        sample_rate_slider.value,
        reflection_slider.value,
        cycle_slider.value,
        node_span_slider.value,
    ) do _...
        recompute()
    end
    on(progress_slider.value) do value
        update_frame(value)
    end
    on(play_button.clicks) do _
        playing[] = !playing[]
        if playing[]
            @async begin
                while playing[]
                    next_value = mod(
                        progress_slider.value[] + playback_slider.value[] * 6,
                        1001,
                    )
                    set_close_to!(progress_slider, round(Int, next_value))
                    sleep(0.03)
                end
            end
        end
    end
    on(reset_button.clicks) do _
        playing[] = false
        set_close_to!(speed_slider, 343)
        set_close_to!(distance_slider, 3.0)
        set_close_to!(frequency_slider, 500)
        set_close_to!(snr_slider, 30)
        set_close_to!(angle_slider, 0)
        set_close_to!(sample_rate_slider, 48000)
        set_close_to!(reflection_slider, 0.75)
        set_close_to!(cycle_slider, 4)
        set_close_to!(node_span_slider, 4)
        set_close_to!(progress_slider, 250)
        set_close_to!(playback_slider, 0.5)
        status[] = "已重置"
    end

    output_dir = get(
        ENV,
        "PHYSICS_SOUND_SPEED_OUTPUT_DIR",
        joinpath(LAB_DIR, "output"),
    )
    on(export_button.clicks) do _
        playing[] = false
        status[] = "正在导出..."
        yield()
        mkpath(output_dir)
        timestamp = Dates.format(now(), "yyyymmdd_HHMMSS")
        prefix = "sound_speed_$(MODE_FILES[mode[]])_$timestamp"
        try
            write_csv(
                joinpath(output_dir, "$prefix.csv"),
                mode[],
                current_parameters[],
                current_data[],
            )
            status[] = "导出完成：output/$prefix"
        catch error
            status[] = "导出失败：$(sprint(showerror, error))"
        end
    end
    colsize!(figure.layout, 1, Relative(0.34))
    colsize!(figure.layout, 2, Relative(0.34))
    colsize!(figure.layout, 3, Relative(0.32))
    rowsize!(figure.layout, 1, 44)
    rowsize!(figure.layout, 2, 26)
    rowsize!(figure.layout, 3, 40)
    rowsize!(figure.layout, 4, 330)
    rowsize!(figure.layout, 5, 230)
    rowsize!(figure.layout, 6, 95)
    rowgap!(figure.layout, 6)
    for column in 1:4
        colsize!(mode_bar, column, Relative(0.25))
        colsize!(analysis, column, Relative(0.25))
    end
    colsize!(controls, 1, Relative(0.34))
    colsize!(controls, 2, Relative(0.34))
    colsize!(controls, 3, Relative(0.32))
    for grid in (basic, special, motion)
        rowgap!(grid, 4)
    end

    update_visibility()
    recompute()
    state = (;
        mode,
        current_data,
        current_parameters,
        progress_slider,
        distance_slider,
        angle_slider,
        frequency_slider,
        reflection_slider,
        cycle_slider,
        middle_curve1,
        echo_curve,
        echo_point,
        dual_curve,
        phase_curve,
    )
    return figure, state
end

function run_model_tests()
    echo = echo_model(343.0, 4.0, 48000.0, 60.0, 0.8)
    @assert abs(echo.estimate - 343.0) / 343.0 < 0.01
    @assert isapprox(echo.delay, 8 / 343; atol = 1.0e-12)

    dual = dual_microphone_model(343.0, 2.0, 30.0, 48000.0, 60.0)
    @assert abs(dual.estimate - 343.0) / 343.0 < 0.01
    @assert dual.best_lag > 0

    phase = phase_model(343.0, 3.0, 500.0, 80.0, 4)
    @assert phase.true_cycles == 4
    @assert abs(phase.estimate - 343.0) / 343.0 < 0.005

    standing = standing_wave_model(343.0, 3.0, 500.0, 0.9, 4, 0.25)
    @assert isapprox(standing.wavelength, 343 / 500; atol = 1.0e-12)
    @assert isapprox(standing.estimate, 343.0; atol = 1.0e-10)

    _, state = build_lab()
    @assert state.mode[] == :echo
    @assert isfinite(state.current_data[].estimate)
    println("四种声速测量模型自检通过：回声、互相关、相位和驻波计算均正常。")
end

const PAGE_STYLE = """
html, body { margin: 0; width: 100%; min-height: 100%; background: #0b0f14; color: #eef3f8; }
body { overflow: hidden; font-family: 'Microsoft YaHei', 'Noto Sans CJK SC', sans-serif; }
.sound-speed-lab { width: 1000px; max-width: 100%; min-height: 828px; margin: 0 auto; padding: 28px 0 0; box-sizing: content-box; overflow: hidden; background: #0b0f14; }
"""

const CLIENT_READY_SCRIPT = """
(() => {
    let sent = false;
    const startedAt = performance.now();
    const send = (type, detail = "") => window.parent.postMessage({ type, detail }, "*");
    const check = () => {
        const canvas = document.querySelector("canvas");
        const spinner = document.querySelector(".wglmakie-spinner");
        const spinnerVisible = spinner && spinner.getClientRects().length > 0;
        if (canvas && !spinnerVisible) {
            if (!sent) send("sound-speed-wgl-ready", "canvas-ready");
            sent = true;
            return;
        }
        if (performance.now() - startedAt > 60000) {
            send("sound-speed-wgl-failed", "WGLMakie 初始化超过 60 秒");
            return;
        }
        window.setTimeout(check, 300);
    };
    window.addEventListener("error", event => send("sound-speed-wgl-failed", event.message));
    check();
})()
"""

function sound_speed_app()
    return Bonito.App(; title = "声速测量综合可视化实验") do
        figure, _ = build_lab()
        DOM.div(
            DOM.style(PAGE_STYLE),
            DOM.div(figure; class = "sound-speed-lab"),
            DOM.script(CLIENT_READY_SCRIPT),
        )
    end
end

function health_app()
    return Bonito.App(
        DOM.pre("physics-experiment:sound-speed");
        title = "physics-experiment:sound-speed",
    )
end

function main()
    load_packaged_wgl_shaders!()
    WGLMakie.activate!(; use_html_widgets = true)
    if "--self-test" in ARGS
        run_model_tests()
        return
    end
    host = get(ENV, "SOUND_SPEED_WEB_HOST", "127.0.0.1")
    port = parse(Int, get(ENV, "SOUND_SPEED_WEB_PORT", "9385"))
    # Keep browser-facing URLs relative so the same process works through
    # localhost and through the server's LAN address.
    proxy_url = strip(get(ENV, "SOUND_SPEED_WEB_PROXY_URL", "."))
    isempty(proxy_url) && (proxy_url = ".")
    server = Bonito.Server(host, port; proxy_url = proxy_url)
    Bonito.route!(server, "/__physics_health__" => health_app())
    Bonito.route!(server, "/" => sound_speed_app())
    println("声速测量网页实验已启动：http://$(host):$(port)")
    wait(server)
end

if abspath(PROGRAM_FILE) == @__FILE__
    main()
end
