using Bonito
using Printf
using WGLMakie

include(joinpath(@__DIR__, "playback_lifecycle.jl"))

const DOM = Bonito.DOM
const Slider = WGLMakie.Makie.Slider
const Button = WGLMakie.Makie.Button
const FIGURE_WIDTH = 1120
const FIGURE_HEIGHT = 720
const PARAMETER_LAB_DIR = @__DIR__
const CJK_PROBE_TEXT = "气体常数测定光栅干涉偏振迈克尔逊波长误差播放暂停复位单步"
const PANEL_BG = RGBf(0.067, 0.078, 0.102)
const PLOT_BG = RGBf(0.047, 0.057, 0.076)
const CYAN = RGBf(0.20, 0.78, 0.94)
const AMBER = RGBf(1.00, 0.66, 0.22)
const GREEN = RGBf(0.32, 0.84, 0.58)
const PINK = RGBf(0.96, 0.38, 0.55)
const MUTED = RGBf(0.61, 0.67, 0.75)
const BUTTON_BG = RGBf(0.12, 0.18, 0.25)
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

function configure_parameter_lab_theme!()
    runtime_font = normpath(joinpath(PARAMETER_LAB_DIR, "..", "..", ".runtime", "fonts", "NotoSansCJKsc-Regular.otf"))
    bundled_font = normpath(joinpath(PARAMETER_LAB_DIR, "..", "assets", "fonts", "NotoSansCJKsc-Regular.otf"))
    julia_font = normpath(joinpath(Sys.BINDIR, "..", "share", "photoelectric", "fonts", "NotoSansCJKsc-Regular.otf"))
    regular = first_cjk_font([
        get(ENV, "PHYSICS_CJK_FONT", ""), runtime_font, bundled_font, julia_font,
        isempty(get(ENV, "WINDIR", "")) ? "" : joinpath(ENV["WINDIR"], "Fonts", "msyh.ttc"),
        "/System/Library/Fonts/PingFang.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc", fontconfig_match("Noto Sans CJK SC:lang=zh-cn"),
    ])
    isnothing(regular) && error("未找到中文字体，请通过 PHYSICS_CJK_FONT 指定。")
    set_theme!(Theme(
        fontsize = 14, font = regular, fonts = (; regular, bold = regular),
        textcolor = :white, backgroundcolor = RGBf(0.035, 0.042, 0.058),
        Axis = (
            backgroundcolor = PLOT_BG,
            xgridcolor = (:white, 0.08), ygridcolor = (:white, 0.08),
            spinecolor = (:white, 0.19), xtickcolor = (:white, 0.26), ytickcolor = (:white, 0.26),
            topspinevisible = false, rightspinevisible = false,
        ),
    ))
end

normalized(value, low, high) = clamp((Float64(value) - Float64(low)) / (Float64(high) - Float64(low)), 0.0, 1.0)
circle_points(cx, cy, radius; count = 121) = [Point2f(cx + radius * cos(t), cy + radius * sin(t)) for t in range(0, 2pi; length = count)]

const PAGE_PHASES = Dict(
    (:gas_gamma, "/process") => ("① 缓慢加压并热平衡", "② 快速放气近似绝热", "③ 立即关闭快速阀", "④ 等容回温读取终态"),
    (:gas_gamma, "/pressure") => ("① 校正 U 管零点", "② 记录 10–30 s 液柱", "③ 记录 40–60 s 液柱", "④ 线性化外推瞬时值"),
    (:gas_gamma, "/gamma") => ("① 输入初态压差", "② 输入回温终态压差", "③ 逐次计算 γᵢ", "④ 比较理论值与均值"),
    (:gas_gamma, "/uncertainty") => ("① 设置重复测量散布", "② 累计 3–5 次测量", "③ 累计 6–10 次测量", "④ 合成 A/B 类不确定度"),
    (:grating_interference, "/principle") => ("① 设置缝数与光栅常数", "② 从负角扫描至零级", "③ 扫描正级主极大", "④ 比较峰宽、暗纹与缺级"),
    (:grating_interference, "/spectrum") => ("① 调整光栅法线", "② 扫描左侧 −k 级谱线", "③ 扫描右侧 +k 级谱线", "④ 左右读数取半差"),
    (:grating_interference, "/wavelength") => ("① 记录零级方向", "② 记录 ±1 级谱线", "③ 记录 ±2、±3 级谱线", "④ 拟合 sinθ–k 斜率"),
    (:grating_interference, "/resolution") => ("① 设置近邻双谱线", "② 增加有效照明刻线数", "③ 检查瑞利判据", "④ 区分分辨本领与测量不确定度"),
    (:light_polarization, "/malus") => ("① 遮光校零并对准透振轴", "② 旋转检偏器 0°–90°", "③ 继续扫描至 180°", "④ 由极值计算消光比"),
    (:light_polarization, "/brewster") => ("① 校正样品转台零位", "② 扫描 p 光反射强度", "③ 寻找反射极小角", "④ 重复三次并反演折射率"),
    (:light_polarization, "/waveplate") => ("① 标定波片快轴", "② 观察相位延迟形成椭圆", "③ 转动检偏器扫描极值", "④ 判别线、椭圆或圆偏振"),
    (:light_polarization, "/fit") => ("① 遮光测量暗电压", "② 每 5°/10° 记录光强", "③ 完成 0°–360° 扫描", "④ 拟合 Stokes 形式并查残差"),
    (:michelson_wavelength, "/alignment") => ("① 分别遮挡两臂调返回光斑", "② 使两返回光斑重合", "③ 插入扩束镜观察条纹", "④ 微调 M₂ 得到同心圆"),
    (:michelson_wavelength, "/counting") => ("① 记录鼓轮起始位置", "② 单向移动 M₁ 并计数", "③ 每 30 条纹记录一组", "④ 累计十组、共 300 条纹"),
    (:michelson_wavelength, "/wavelength") => ("① 检查位移零点", "② 揭示前三组数据", "③ 完成十组数据采集", "④ 拟合 Δd=a+(λ/2)N"),
    (:michelson_wavelength, "/uncertainty") => ("① 设置鼓轮分辨力", "② 检查单向逼近数据", "③ 演示换向空程偏差", "④ 合成位移与计数不确定度"),
)

function phase_description(key, page, progress)
    phases = get(PAGE_PHASES, (key, String(page)), ("① 准备", "② 扫描", "③ 记录", "④ 分析"))
    index = clamp(floor(Int, Float64(progress) * 4) + 1, 1, 4)
    return phases[index]
end

function apparatus_axis(slot, title)
    ax = Axis(slot, title = title, backgroundcolor = PANEL_BG, aspect = DataAspect())
    limits!(ax, 0, 10, 0, 6)
    hidedecorations!(ax)
    hidespines!(ax)
    return ax
end

function draw_gas_apparatus!(slot, cfg, value, progress)
    ax = apparatus_axis(slot, "Clément–Desormes 装置与状态")
    lines!(ax, [1.0, 1.0, 5.2, 5.2, 1.0], [1.0, 4.7, 4.7, 1.0, 1.0]; color = CYAN, linewidth = 3)
    lines!(ax, [3.1, 3.1, 3.8], [4.7, 5.45, 5.45]; color = :white, linewidth = 5)
    scatter!(ax, [3.82], [5.45]; marker = :rect, markersize = 16, color = AMBER)
    text!(ax, 1.15, 5.15; text = "贮气瓶", color = MUTED, fontsize = 13)
    text!(ax, 3.95, 5.35; text = "快速阀", color = MUTED, fontsize = 12)
    lines!(ax, [6.1, 6.1, 6.1, 8.4, 8.4, 8.4], [4.8, 1.0, 0.65, 0.65, 1.0, 4.8]; color = RGBf(0.72, 0.78, 0.86), linewidth = 4)
    level_delta = @lift begin
        base = 0.35 + 1.0 * normalized($value, cfg.vmin, cfg.vmax)
        p = $progress
        base * (p < 0.32 ? 1.0 : p < 0.48 ? 0.08 : 0.08 + 0.34 * (p - 0.48) / 0.52)
    end
    left_y = @lift(2.55 + $level_delta / 2)
    right_y = @lift(2.55 - $level_delta / 2)
    lines!(ax, @lift([Point2f(6.1, $left_y), Point2f(6.1, 0.8), Point2f(8.4, 0.8), Point2f(8.4, $right_y)]); color = AMBER, linewidth = 12)
    lines!(ax, [5.2, 6.1], [3.4, 3.4]; color = CYAN, linewidth = 3)
    text!(ax, 6.1, 5.15; text = "U 形压差计", color = MUTED, fontsize = 13)
    molecule_points = @lift begin
        spread = 0.75 + 0.55 * $progress
        [Point2f(1.45 + mod(0.71i + 0.18sin(2pi * $progress + i), 3.25),
                 1.35 + mod(spread * (0.43i + 0.12cos(2pi * $progress + i)), 2.85)) for i in 1:24]
    end
    scatter!(ax, molecule_points; color = (:white, 0.72), markersize = 5)
    return ax
end

function draw_grating_apparatus!(slot, cfg, value, progress)
    ax = apparatus_axis(slot, "分光计光路与 ±k 级谱线")
    scatter!(ax, [0.9], [3.0]; marker = :rect, markersize = 24, color = AMBER)
    text!(ax, 0.35, 3.5; text = "准直光", color = MUTED, fontsize = 12)
    lines!(ax, [1.1, 4.35], [3.0, 3.0]; color = AMBER, linewidth = 4)
    for y in range(1.35, 4.65; length = 13)
        lines!(ax, [4.4, 4.4], [y - 0.11, y + 0.11]; color = CYAN, linewidth = 3)
    end
    text!(ax, 3.75, 5.05; text = "平面光栅", color = MUTED, fontsize = 12)
    lines!(ax, [9.25, 9.25], [0.65, 5.35]; color = (:white, 0.5), linewidth = 4)
    angle_scale = @lift(1.25 + 1.15 * normalized($value, cfg.vmin, cfg.vmax))
    for (order, color) in zip((-2, -1, 0, 1, 2), (PINK, GREEN, :white, GREEN, PINK))
        end_y = @lift(3.0 + order * $angle_scale * 0.72)
        lines!(ax, @lift([Point2f(4.45, 3.0), Point2f(9.2, $end_y)]); color = color, linewidth = order == 0 ? 2 : 3)
        scatter!(ax, @lift([Point2f(9.2, $end_y)]); color = color, markersize = order == 0 ? 9 : 13)
    end
    photon = @lift begin
        p = $progress
        p < 0.45 ? Point2f(1.1 + 3.35 * p / 0.45, 3.0) : Point2f(4.45 + 4.75 * (p - 0.45) / 0.55, 3.0 + 1.45 * (p - 0.45) / 0.55)
    end
    scatter!(ax, @lift([$photon]); color = :yellow, markersize = 12, glowwidth = 8, glowcolor = (:yellow, 0.35))
    text!(ax, 8.35, 5.55; text = "接收屏", color = MUTED, fontsize = 12)
    return ax
end

function draw_polarization_apparatus!(slot, page, cfg, value, progress)
    if page == "/brewster"
        ax = apparatus_axis(slot, "布儒斯特角：p 光反射极小")
        lines!(ax, [0.5, 9.5], [2.35, 2.35]; color = CYAN, linewidth = 5)
        lines!(ax, [5.0, 5.0], [0.5, 5.5]; color = (:white, 0.35), linestyle = :dash, linewidth = 2)
        incidence = @lift(deg2rad(18 + 67 * $progress))
        refractive_index = @lift(Float64($value))
        source = @lift(Point2f(5.0 - 3.6sin($incidence), 2.35 + 3.6cos($incidence)))
        reflected = @lift(Point2f(5.0 + 3.6sin($incidence), 2.35 + 3.6cos($incidence)))
        refraction = @lift(asin(clamp(sin($incidence) / $refractive_index, -1, 1)))
        transmitted = @lift(Point2f(5.0 + 2.7sin($refraction), 2.35 - 2.7cos($refraction)))
        lines!(ax, @lift([$source, Point2f(5.0, 2.35)]); color = AMBER, linewidth = 4)
        lines!(ax, @lift([Point2f(5.0, 2.35), $reflected]); color = PINK, linewidth = 3)
        lines!(ax, @lift([Point2f(5.0, 2.35), $transmitted]); color = GREEN, linewidth = 3)
        scatter!(ax, @lift([$source]); marker = :rect, markersize = 22, color = AMBER)
        rp = @lift begin
            i = $incidence
            n = $refractive_index
            t = asin(clamp(sin(i) / n, -1, 1))
            abs2(tan(i - t) / max(abs(tan(i + t)), 1e-8))
        end
        scatter!(ax, @lift([$reflected]); markersize = @lift(8 + 24sqrt(clamp($rp, 0, 1))), color = PINK)
        text!(ax, 0.55, 5.45; text = "p 偏振入射光", color = MUTED, fontsize = 12)
        text!(ax, 7.2, 5.25; text = "反射光", color = PINK, fontsize = 12)
        text!(ax, 7.25, 0.55; text = "折射光", color = GREEN, fontsize = 12)
        angle_readout = @lift(@sprintf("i = %.1f°   iᴮ = %.1f°", rad2deg($incidence), rad2deg(atan($refractive_index))))
        text!(ax, 4.15, 0.55; text = angle_readout, color = :white, fontsize = 12)
        return ax
    elseif page == "/waveplate"
        ax = apparatus_axis(slot, "波片快慢轴与偏振椭圆")
        lines!(ax, [0.6, 9.4], [2.5, 2.5]; color = (:white, 0.22), linewidth = 2)
        scatter!(ax, [0.75], [2.5]; marker = :rect, markersize = 23, color = AMBER)
        lines!(ax, circle_points(2.6, 2.5, 0.72); color = CYAN, linewidth = 3)
        lines!(ax, [2.6, 2.6], [1.85, 3.15]; color = GREEN, linewidth = 4)
        scatter!(ax, [5.0], [2.5]; marker = :rect, markersize = (24, 68), color = (:cyan, 0.22), strokecolor = CYAN, strokewidth = 2)
        lines!(ax, [4.62, 5.38], [2.12, 2.88]; color = PINK, linewidth = 3)
        lines!(ax, [4.62, 5.38], [2.88, 2.12]; color = (:white, 0.55), linewidth = 2)
        text!(ax, 1.85, 3.55; text = "起偏器", color = MUTED, fontsize = 12)
        text!(ax, 4.15, 3.55; text = "波片快/慢轴", color = MUTED, fontsize = 12)
        delta = @lift(deg2rad(Float64($value)))
        ellipse = @lift([Point2f(7.7 + 1.05cos(t), 4.35 + 1.05cos(t + $delta)) for t in range(0, 2pi; length = 161)])
        lines!(ax, ellipse; color = AMBER, linewidth = 3.5)
        vector_tip = @lift(Point2f(7.7 + 1.05cos(2pi*$progress), 4.35 + 1.05cos(2pi*$progress + $delta)))
        lines!(ax, @lift([Point2f(7.7, 4.35), $vector_tip]); color = CYAN, linewidth = 3)
        scatter!(ax, @lift([$vector_tip]); color = :yellow, markersize = 10)
        text!(ax, 6.75, 5.65; text = "电矢量端点轨迹", color = MUTED, fontsize = 12)
        return ax
    end

    ax = apparatus_axis(slot, page == "/fit" ? "自动检偏扫描与光电采集" : "起偏—检偏—探测光路")
    lines!(ax, [0.7, 9.4], [3.0, 3.0]; color = (:white, 0.22), linewidth = 2)
    scatter!(ax, [0.8], [3.0]; marker = :rect, markersize = 25, color = AMBER)
    for (x, label) in ((3.0, "起偏器"), (6.1, "检偏器"))
        lines!(ax, circle_points(x, 3.0, 0.95); color = CYAN, linewidth = 3)
        text!(ax, x - 0.55, 4.25; text = label, color = MUTED, fontsize = 12)
    end
    lines!(ax, [3.0, 3.0], [2.15, 3.85]; color = GREEN, linewidth = 4)
    analyzer_angle = @lift(2pi * $progress)
    analyzer_axis = @lift begin
        a = $analyzer_angle
        [Point2f(6.1 - 0.85cos(a), 3.0 - 0.85sin(a)), Point2f(6.1 + 0.85cos(a), 3.0 + 0.85sin(a))]
    end
    lines!(ax, analyzer_axis; color = PINK, linewidth = 4)
    intensity = @lift begin
        p = normalized($value, cfg.vmin, cfg.vmax)
        (1 - p) / 2 + p * cos(2pi * $progress)^2
    end
    detector_color = @lift(RGBAf(1.0, 0.72, 0.18, 0.18 + 0.82 * $intensity))
    scatter!(ax, [9.0], [3.0]; marker = :rect, markersize = 42, color = detector_color)
    text!(ax, 8.35, 4.0; text = "光电探测器", color = MUTED, fontsize = 12)
    electric_wave = @lift begin
        amplitude = 0.12 + 0.52 * sqrt($intensity)
        [Point2f(x, 3.0 + amplitude * sin(9x - 2pi * $progress)) for x in range(1.1, 8.65; length = 160)]
    end
    lines!(ax, electric_wave; color = AMBER, linewidth = 2.5)
    return ax
end

function draw_michelson_apparatus!(slot, page, cfg, value, progress)
    title = page == "/counting" ? "移镜、条纹吞吐与累计计数" : page == "/uncertainty" ? "双臂光路与回程差检查" : "迈克尔逊干涉仪光路与条纹"
    ax = apparatus_axis(slot, title)
    scatter!(ax, [0.75], [2.7]; marker = :rect, markersize = 24, color = AMBER)
    text!(ax, 0.25, 3.25; text = "He–Ne", color = MUTED, fontsize = 12)
    lines!(ax, [1.0, 4.35], [2.7, 2.7]; color = AMBER, linewidth = 4)
    lines!(ax, [4.1, 4.75], [2.25, 3.05]; color = CYAN, linewidth = 5)
    text!(ax, 3.45, 1.85; text = "分光板", color = MUTED, fontsize = 12)
    scan_gain = page == "/counting" ? 0.42 : page == "/wavelength" ? 0.36 : page == "/uncertainty" ? 0.18 : 0.0
    mirror_shift = @lift(0.16 * normalized($value, cfg.vmin, cfg.vmax) + scan_gain * $progress)
    mirror_x = @lift(8.1 + $mirror_shift)
    lines!(ax, @lift([Point2f($mirror_x, 1.65), Point2f($mirror_x, 3.75)]); color = :white, linewidth = 7)
    lines!(ax, [3.4, 5.45], [5.2, 5.2]; color = :white, linewidth = 7)
    text!(ax, 8.0, 1.15; text = "M₁ 可动镜", color = MUTED, fontsize = 12)
    text!(ax, 2.3, 5.35; text = "M₂ 固定镜", color = MUTED, fontsize = 12)
    lines!(ax, @lift([Point2f(4.45, 2.7), Point2f($mirror_x, 2.7), Point2f(4.45, 2.7)]); color = PINK, linewidth = 3)
    lines!(ax, [4.45, 4.45, 4.45], [2.7, 5.15, 2.7]; color = GREEN, linewidth = 3)
    lines!(ax, [4.45, 6.15], [2.7, 0.85]; color = CYAN, linewidth = 3)
    text!(ax, 5.8, 0.5; text = "观察屏", color = MUTED, fontsize = 12)
    center = Point2f(7.5, 4.8)
    fringe_cycles = page == "/counting" ? 10.0 : page == "/wavelength" ? 8.0 : 4.0
    fringe_phase = @lift(mod(fringe_cycles * $progress, 1.0))
    for order in 1:5
        ring = @lift begin
            radius = 0.16 + 0.44sqrt(max(order - $fringe_phase, 0.04))
            circle_points(center[1], center[2], radius)
        end
        alpha = @lift(0.38 + 0.52 * (1.0 - $fringe_phase))
        lines!(ax, ring; color = @lift(RGBAf(0.35, 0.85, 1.0, $alpha)), linewidth = 3)
    end
    photon = @lift begin
        p = mod(2 * $progress, 1.0)
        p < 0.5 ? Point2f(4.45 + (2p) * ($mirror_x - 4.45), 2.7) : Point2f($mirror_x - (2p - 1) * ($mirror_x - 4.45), 2.7)
    end
    scatter!(ax, @lift([$photon]); color = :yellow, markersize = 11)
    if page == "/counting"
        fringe_readout = @lift(@sprintf("累计 N = %d 条", floor(Int, 300 * $progress)))
        text!(ax, 6.25, 0.35; text = fringe_readout, color = AMBER, fontsize = 13)
    elseif page == "/uncertainty"
        text!(ax, 6.0, 0.35; text = "换向前先走完机械空程", color = PINK, fontsize = 12)
    end
    return ax
end

function draw_apparatus!(slot, page, cfg, value, progress)
    key = LAB_SPEC.key
    key == :gas_gamma && return draw_gas_apparatus!(slot, cfg, value, progress)
    key == :grating_interference && return draw_grating_apparatus!(slot, cfg, value, progress)
    key == :light_polarization && return draw_polarization_apparatus!(slot, page, cfg, value, progress)
    return draw_michelson_apparatus!(slot, page, cfg, value, progress)
end

function bind_transport!(controls, scan_slider, speed_slider, reset_sliders, recorded_x, recorded_y, scan_x, scan_y)
    playing = Observable(false)
    generation = Ref(0)
    buttons = GridLayout()
    controls[1:4, 4] = buttons
    play_button = Button(buttons[1, 1], label = "播放", height = 31, buttoncolor = BUTTON_BG, labelcolor = :white)
    step_button = Button(buttons[1, 2], label = "单步", height = 31, buttoncolor = BUTTON_BG, labelcolor = :white)
    record_button = Button(buttons[2, 1], label = "记录", height = 31, buttoncolor = BUTTON_BG, labelcolor = :white)
    clear_button = Button(buttons[2, 2], label = "清空", height = 31, buttoncolor = BUTTON_BG, labelcolor = :white)
    reset_button = Button(buttons[3, 1:2], label = "复位", height = 31, buttoncolor = BUTTON_BG, labelcolor = :white)
    on(play_button.clicks) do _
        playing[] = !playing[]
        generation[] += 1
        token = generation[]
        play_button.label[] = playing[] ? "暂停" : "播放"
        if playing[]
            @async begin
                while playing[] && token == generation[]
                    current = Int(round(scan_slider.value[]))
                    set_close_to!(scan_slider, current >= 100 ? 0 : current + 1)
                    sleep(0.055 / max(Float64(speed_slider.value[]), 0.25))
                end
            end
        end
    end
    cancel_playback! = () -> begin
        playing[] = false
        generation[] += 1
        play_button.label[] = "播放"
        nothing
    end
    register_playback_cancel!(cancel_playback!)
    on(step_button.clicks) do _
        playing[] = false
        generation[] += 1
        play_button.label[] = "播放"
        current = Int(round(scan_slider.value[]))
        set_close_to!(scan_slider, current >= 100 ? 0 : min(100, current + 5))
    end
    on(record_button.clicks) do _
        push!(recorded_x[], Float64(scan_x[]))
        push!(recorded_y[], Float64(scan_y[]))
        notify(recorded_x)
        notify(recorded_y)
    end
    on(clear_button.clicks) do _
        empty!(recorded_x[])
        empty!(recorded_y[])
        notify(recorded_x)
        notify(recorded_y)
    end
    on(reset_button.clicks) do _
        playing[] = false
        generation[] += 1
        play_button.label[] = "播放"
        for (slider, default) in reset_sliders
            set_close_to!(slider, default)
        end
        empty!(recorded_x[])
        empty!(recorded_y[])
        notify(recorded_x)
        notify(recorded_y)
    end
    return (; playing, play_button, step_button, record_button, clear_button, reset_button)
end

function build_page(page)
    configure_parameter_lab_theme!()
    cfg = LAB_SPEC.pages[page]
    xs = collect(range(cfg.xmin, cfg.xmax; length = 501))
    value = Observable(Float64(cfg.default))
    scan_percent = Observable(0.0)
    instrument_bias = Observable(0.0)
    recorded_x = Observable(Float64[])
    recorded_y = Observable(Float64[])
    progress = @lift(Float64($scan_percent) / 100.0)
    ys = @lift(Float64.(cfg.model(xs, $value)))
    scan_x = @lift(cfg.xmin + $progress * (cfg.xmax - cfg.xmin))
    theoretical_scan_y = @lift(Float64(first(cfg.model([$scan_x], $value))))
    scan_y = @lift($theoretical_scan_y * (1.0 + $instrument_bias / 100.0))
    visible_ys = @lift begin
        current_ys = $ys
        stop = clamp(floor(Int, $progress * (length(xs) - 1)) + 1, 1, length(xs))
        [i <= stop ? current_ys[i] : NaN for i in eachindex(xs)]
    end

    fig = Figure(size = (FIGURE_WIDTH, FIGURE_HEIGHT), figure_padding = (16, 16, 12, 12))
    Label(fig[1, 1:2], "$(LAB_SPEC.title)  ·  $(cfg.title)"; fontsize = 23, color = RGBf(0.94, 0.97, 1.0), halign = :left)
    ax = Axis(fig[2, 1], xlabel = cfg.xlabel, ylabel = cfg.ylabel, title = "理论模型与动态测量轨迹")
    lines!(ax, xs, ys; linewidth = 2, color = (:white, 0.20), label = "理论全程")
    lines!(ax, xs, visible_ys; linewidth = 3.5, color = AMBER, label = "已扫描")
    scatter!(ax, recorded_x, recorded_y; markersize = 9, color = GREEN, strokecolor = :white, strokewidth = 0.8, label = "已记录")
    scatter!(ax, scan_x, scan_y; markersize = 14, color = CYAN, strokecolor = :white, strokewidth = 1.5)
    limit_samples = Float64[]
    for candidate in (cfg.vmin, cfg.default, cfg.vmax)
        append!(limit_samples, Float64.(cfg.model(xs, candidate)))
    end
    filter!(isfinite, limit_samples)
    if !isempty(limit_samples)
        lower, upper = extrema(limit_samples)
        span = upper - lower
        padding = span > 1e-9 ? 0.08span : max(0.15max(abs(lower), abs(upper)), 0.1)
        axis_lower = lower >= -1e-10 ? max(0.0, lower - padding) : lower - padding
        ylims!(ax, axis_lower, upper + padding)
    end
    axislegend(ax; position = :rt, framevisible = false, labelsize = 11)

    apparatus = GridLayout()
    fig[2, 2] = apparatus
    draw_apparatus!(apparatus[1, 1], page, cfg, value, progress)
    Label(apparatus[2, 1], @lift(phase_description(LAB_SPEC.key, page, $progress)); color = GREEN, fontsize = 12.5, tellwidth = false)
    rowsize!(apparatus, 2, 26)

    controls = GridLayout()
    fig[3, 1:2] = controls
    Label(controls[1, 1], cfg.control; halign = :right, color = MUTED)
    parameter_slider = Slider(controls[1, 2], range = range(cfg.vmin, cfg.vmax; length = 121), startvalue = cfg.default, update_while_dragging = false)
    connect!(value, parameter_slider.value)
    Label(controls[1, 3], @lift(@sprintf("%s = %.4g %s", cfg.symbol, $value, cfg.unit)); halign = :left, color = GREEN)
    Label(controls[2, 1], "测量进程"; halign = :right, color = MUTED)
    scan_slider = Slider(controls[2, 2], range = 0:100, startvalue = 0, update_while_dragging = true)
    connect!(scan_percent, scan_slider.value)
    Label(controls[2, 3], @lift(@sprintf("%.0f %%", $scan_percent)); halign = :left, color = CYAN)
    Label(controls[3, 1], "仪器偏差"; halign = :right, color = MUTED)
    bias_slider = Slider(controls[3, 2], range = -5.0:0.25:5.0, startvalue = 0.0, update_while_dragging = false)
    connect!(instrument_bias, bias_slider.value)
    Label(controls[3, 3], @lift(@sprintf("%+.2f %%", $instrument_bias)); halign = :left, color = PINK)
    Label(controls[4, 1], "播放速度"; halign = :right, color = MUTED)
    speed_slider = Slider(controls[4, 2], range = 0.25:0.25:2.0, startvalue = 1.0, update_while_dragging = false)
    Label(controls[4, 3], @lift(@sprintf("%.2f ×", $(speed_slider.value))); halign = :left, color = AMBER)
    bind_transport!(controls, scan_slider, speed_slider,
        ((parameter_slider, cfg.default), (scan_slider, 0), (bias_slider, 0.0), (speed_slider, 1.0)),
        recorded_x, recorded_y, scan_x, scan_y)
    colsize!(controls, 1, Fixed(118)); colsize!(controls, 2, Relative(0.62)); colsize!(controls, 3, Fixed(150)); colsize!(controls, 4, Fixed(226))
    for row in 1:4
        rowsize!(controls, row, 27)
    end
    rowgap!(controls, 4)

    metrics = GridLayout()
    fig[4, 1:2] = metrics
    Label(metrics[1, 1], @lift(@sprintf("控制量\n%s = %.5g %s", cfg.symbol, $value, cfg.unit)); halign = :left, color = GREEN, fontsize = 13)
    Label(metrics[1, 2], @lift(@sprintf("扫描读数\nx = %.5g", $scan_x)); halign = :left, color = CYAN, fontsize = 13)
    Label(metrics[1, 3], @lift(@sprintf("模拟测量\ny = %.5g（偏差 %+.2f%%）", $scan_y, $instrument_bias)); halign = :left, color = AMBER, fontsize = 12.5)
    Label(metrics[1, 4], @lift("实验阶段 / 已记录 $(length($(recorded_x))) 点\n" * phase_description(LAB_SPEC.key, page, $progress)); halign = :left, color = PINK, fontsize = 12.2, tellwidth = false)
    Label(metrics[2, 1:2], "关系式：$(cfg.formula)"; halign = :left, color = RGBf(0.91, 0.94, 0.98), fontsize = 12.5, tellwidth = false)
    Label(metrics[2, 3:4], "操作要点：$(cfg.note)"; halign = :left, color = MUTED, fontsize = 12.2, tellwidth = false)
    Label(metrics[3, 1:4], "设计依据：$(LAB_SPEC.reference)"; halign = :left, color = RGBf(0.48, 0.70, 0.84), fontsize = 11.5, tellwidth = false)
    for column in 1:4
        colsize!(metrics, column, Relative(0.25))
    end
    rowsize!(metrics, 1, 46); rowsize!(metrics, 2, 30); rowsize!(metrics, 3, 23); rowgap!(metrics, 3)
    rowsize!(fig.layout, 1, 36); rowsize!(fig.layout, 2, 350); rowsize!(fig.layout, 3, 128); rowsize!(fig.layout, 4, 112)
    colsize!(fig.layout, 1, Relative(0.59)); colsize!(fig.layout, 2, Relative(0.41)); rowgap!(fig.layout, 7); colgap!(fig.layout, 12)
    return fig
end

const PAGE_STYLE = """
html,body{margin:0;background:#0e1117;overflow:hidden;width:100%;height:100%}
.parameter-stage{position:absolute;inset:0;overflow:hidden}
.parameter-lab{position:absolute;left:0;top:0;width:$(FIGURE_WIDTH)px;height:$(FIGURE_HEIGHT)px;transform-origin:top left}
.parameter-diagnostic{position:fixed;left:16px;right:16px;bottom:16px;z-index:1002;display:none;
 padding:10px 12px;color:#f7d7d7;background:rgba(64,20,28,.94);border:1px solid rgba(255,85,105,.65);
 border-radius:6px;font:13px/1.5 ui-monospace,Consolas,monospace;white-space:pre-wrap}
.parameter-diagnostic.visible{display:block}
"""
const CLIENT_SCRIPT = """
(() => {
  let ready = false;
  let layoutScale = 1;
  const root = document.querySelector('.parameter-lab');
  const resize = () => {
    const scale = Math.min(1.05, (window.innerWidth - 12) / $(FIGURE_WIDTH), (window.innerHeight - 8) / $(FIGURE_HEIGHT));
    layoutScale = scale;
    root.style.transform = `scale(\${scale})`;
    root.style.left = `\${Math.max(0, (window.innerWidth - $(FIGURE_WIDTH) * scale) / 2)}px`;
    root.style.top = `\${Math.max(0, (window.innerHeight - $(FIGURE_HEIGHT) * scale) / 2)}px`;
  };
  const syncPointer = event => {
    const canvas = event.target instanceof HTMLCanvasElement ? event.target : null;
    const screen = canvas && canvas.wglmakie_screen;
    if (!screen || !Number.isFinite(screen.winscale) || screen.winscale <= 0) return;
    if (!Number.isFinite(screen.__physicsBaseWinscale)) screen.__physicsBaseWinscale = screen.winscale;
    const base = screen.__physicsBaseWinscale;
    screen.winscale = base * layoutScale;
    clearTimeout(screen.__physicsPointerScaleTimer);
    screen.__physicsPointerScaleTimer = setTimeout(() => {
      if (canvas.wglmakie_screen === screen) screen.winscale = base;
    }, 120);
  };
  resize();
  window.addEventListener('resize', resize);
  if (window.ResizeObserver) new ResizeObserver(resize).observe(document.documentElement);
  for (const name of ['mousemove','mousedown','mouseup','pointerdown','pointermove','pointerup','wheel']) {
    document.addEventListener(name, syncPointer, {capture:true, passive:true});
  }
  const send = (type, detail='') => window.parent.postMessage({type, detail}, '*');
  const fail = detail => {
    if (ready) return;
    let box = document.querySelector('.parameter-diagnostic');
    if (!box) {
      box = document.createElement('div');
      box.className = 'parameter-diagnostic';
      document.body.appendChild(box);
    }
    box.textContent = detail;
    box.classList.add('visible');
    send('$(LAB_SPEC.failed_event)', detail);
  };
  let glStatus = 'none';
  try {
    const probe = document.createElement('canvas');
    glStatus = probe.getContext('webgl2') ? 'webgl2' : (probe.getContext('webgl') ? 'webgl1' : 'none');
  } catch (error) { glStatus = 'error: ' + error.message; }
  if (glStatus === 'none' || glStatus.startsWith('error:')) {
    fail('浏览器无法创建 WebGL 上下文：' + glStatus);
    return;
  }
  const started = performance.now();
  const check = () => {
    const canvas = document.querySelector('canvas');
    const spinner = document.querySelector('.wglmakie-spinner');
    const spinnerVisible = Boolean(spinner && spinner.getClientRects().length > 0 && getComputedStyle(spinner).visibility !== 'hidden');
    if (canvas && canvas.width > 0 && canvas.height > 0 && !spinnerVisible) {
      ready = true;
      send('$(LAB_SPEC.ready_event)', glStatus);
      return;
    }
    if (performance.now() - started > 75000) {
      fail('WGLMakie/Bonito 初始化超过 75 秒。\\nWebGL 状态：' + glStatus + '\\n页面地址：' + location.href);
      return;
    }
    setTimeout(check, 300);
  };
  window.addEventListener('error', event => fail('浏览器脚本错误：' + event.message));
  window.addEventListener('unhandledrejection', event => fail('浏览器 Promise 错误：' + String(event.reason)));
  check();
})();
"""

function app_for(page)
    App(; title = "$(LAB_SPEC.title) · $(LAB_SPEC.pages[page].title)") do session::Bonito.Session
        playback = build_with_playback_lifecycle(session, () -> build_page(page))
        DOM.div(DOM.style(PAGE_STYLE), DOM.div(DOM.div(playback.figure; class = "parameter-lab"); class = "parameter-stage"), playback.lifecycle_script, DOM.script(CLIENT_SCRIPT))
    end
end

routes = Dict("/" => app_for(first(keys(LAB_SPEC.pages))))
for (path, _) in LAB_SPEC.pages
    routes[path] = app_for(path)
end
routes["/__physics_health__"] = App(DOM.div(LAB_SPEC.marker); title = LAB_SPEC.marker)

if "--self-test" in ARGS
    @assert length(LAB_SPEC.pages) == 4
    @assert all(startswith(path, "/") for path in keys(LAB_SPEC.pages))
    @assert LAB_SPEC.key in (:gas_gamma, :grating_interference, :light_polarization, :michelson_wavelength)
    println("$(LAB_SPEC.title) self-test passed")
    exit()
end

load_packaged_wgl_shaders!()
WGLMakie.activate!(; use_html_widgets = true)
host = get(ENV, LAB_SPEC.host_env, "127.0.0.1")
port = parse(Int, get(ENV, LAB_SPEC.port_env, string(LAB_SPEC.port)))
proxy = strip(get(ENV, LAB_SPEC.proxy_env, "."))
isempty(proxy) && (proxy = ".")
server = Server(host, port; proxy_url = proxy)
for (path, app) in routes
    Bonito.route!(server, path => app)
end
println("$(LAB_SPEC.title) listening on http://$(host):$(port)")
wait(server)
