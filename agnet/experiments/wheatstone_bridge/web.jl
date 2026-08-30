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
const CYAN = RGBf(0.18, 0.78, 0.92)
const PINK = RGBf(0.94, 0.35, 0.50)
const AMBER = RGBf(1.00, 0.72, 0.24)
const GREEN = RGBf(0.36, 0.82, 0.55)
const VIOLET = RGBf(0.61, 0.48, 0.92)
const MUTED = RGBf(0.58, 0.62, 0.70)
const PANEL_BG = RGBf(0.075, 0.085, 0.105)
const BUTTON_BG = RGBf(0.13, 0.15, 0.19)
const CJK_PROBE_TEXT = "惠斯通电桥测电阻桥臂平衡检流计灵敏度误差拟合不确定度"
const HEALTH_MARKER = "physics-experiment:wheatstone-bridge"
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
    rowsize!(figure.layout, 1, 350)
    rowsize!(figure.layout, 2, 176)
    rowsize!(figure.layout, 3, 118)
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
    intercept_uncertainty = sqrt(
        max(residual_variance, 0.0) *
        (1.0 / length(xf) + xbar^2 / sxx),
    )
    total_variation = sum(abs2, yf .- ybar)
    r_squared = total_variation > 0 ? 1.0 - sum(abs2, residuals) / total_variation : 1.0
    return (;
        slope,
        intercept,
        predicted,
        residuals,
        slope_uncertainty,
        intercept_uncertainty,
        r_squared,
    )
end

parallel_resistance(a, b) = Float64(a) * Float64(b) / (Float64(a) + Float64(b))

function validate_bridge_inputs(p, q, standard, unknown, supply, galvanometer)
    all(value -> Float64(value) > 0, (p, q, standard, unknown, supply, galvanometer)) ||
        throw(ArgumentError("桥臂电阻、电源电压与检流计内阻必须大于零"))
    return nothing
end

function detector_current(p, q, standard, unknown, supply, galvanometer)
    validate_bridge_inputs(p, q, standard, unknown, supply, galvanometer)
    left_potential = Float64(supply) * Float64(q) / (Float64(p) + Float64(q))
    right_potential = Float64(supply) * Float64(unknown) / (
        Float64(standard) + Float64(unknown)
    )
    open_voltage = left_potential - right_potential
    thevenin_resistance =
        parallel_resistance(p, q) + parallel_resistance(standard, unknown)
    current = open_voltage / (Float64(galvanometer) + thevenin_resistance)
    return (; left_potential, right_potential, open_voltage, thevenin_resistance, current)
end

function bridge_model(p, q, standard, unknown, supply, galvanometer)
    detector = detector_current(p, q, standard, unknown, supply, galvanometer)
    inferred_unknown = Float64(q) * Float64(standard) / Float64(p)
    balanced_standard = Float64(p) * Float64(unknown) / Float64(q)
    r_min = max(0.01, 0.35 * balanced_standard)
    r_max = 1.65 * balanced_standard
    standard_values = collect(range(r_min, r_max; length = 241))
    current_values = [
        1.0e6 * detector_current(
            p,
            q,
            resistance,
            unknown,
            supply,
            galvanometer,
        ).current
        for resistance in standard_values
    ]
    return (;
        p = Float64(p),
        q = Float64(q),
        standard = Float64(standard),
        unknown = Float64(unknown),
        supply = Float64(supply),
        galvanometer = Float64(galvanometer),
        detector,
        inferred_unknown,
        balanced_standard,
        standard_values,
        current_values,
        ratio = Float64(p) / Float64(q),
        relative_error_percent =
            100.0 * (inferred_unknown - Float64(unknown)) / Float64(unknown),
        null_residual_uv = 1.0e6 * detector.open_voltage,
        current_ua = 1.0e6 * detector.current,
    )
end

function draw_bridge!(axis)
    hidedecorations!(axis)
    hidespines!(axis)
    xlims!(axis, -3.4, 3.4)
    ylims!(axis, -3.8, 3.8)
    for (x, y) in (
        ([-2.0, 0.0], [0.0, 3.0]),
        ([-2.0, 0.0], [0.0, -3.0]),
        ([0.0, 2.0], [3.0, 0.0]),
        ([2.0, 0.0], [0.0, -3.0]),
    )
        lines!(axis, x, y, color = MUTED, linewidth = 5)
    end
    lines!(axis, [-2.0, 2.0], [0.0, 0.0], color = CYAN, linewidth = 2.8)
    scatter!(axis, [0.0, -2.0, 2.0, 0.0], [3.0, 0.0, 0.0, -3.0], color = AMBER, markersize = 15)
    scatter!(axis, [0.0], [0.0], color = PINK, marker = :diamond, markersize = 20)
    text!(axis, "P", position = (-1.22, 1.72), color = :white, fontsize = 18)
    text!(axis, "Q", position = (-1.24, -1.72), color = :white, fontsize = 18)
    text!(axis, "R", position = (1.15, 1.72), color = :white, fontsize = 18)
    text!(axis, "Rₓ", position = (1.12, -1.72), color = :white, fontsize = 18)
    text!(axis, "G", position = (-0.12, 0.28), color = PINK, fontsize = 18)
    text!(axis, "电源 E", position = (-0.42, 3.30), color = AMBER, fontsize = 15)
    text!(axis, "零电流平衡：P/Q=R/Rₓ", position = (-1.55, -3.55), color = GREEN, fontsize = 14)
    return nothing
end

function principle_figure()
    figure, controls, metrics = base_figure()
    circuit_axis = Axis(figure[1, 1], title = "惠斯通电桥桥路与四臂命名")
    null_axis = Axis(
        figure[1, 2],
        title = "检流计零示法",
        xlabel = "可调标准电阻 R / Ω",
        ylabel = "检流计电流 I_G / μA",
    )
    draw_bridge!(circuit_axis)

    p = add_slider!(controls, 1, "比例臂 P", 100:50:1000, 500, value -> @sprintf("%.0f Ω", value))
    q = add_slider!(controls, 2, "比例臂 Q", 100:50:1000, 500, value -> @sprintf("%.0f Ω", value))
    standard = add_slider!(controls, 3, "标准臂 R", 100:5:1000, 470, value -> @sprintf("%.0f Ω", value))
    unknown = add_slider!(controls, 4, "待测电阻 Rₓ", 100:5:1000, 470, value -> @sprintf("%.0f Ω", value))
    supply = add_slider!(controls, 5, "电源电压 E", 1.0:0.5:12.0, 6.0, value -> @sprintf("%.1f V", value))
    galvanometer = add_slider!(controls, 6, "检流计内阻 R_G", 50:25:1000, 300, value -> @sprintf("%.0f Ω", value))

    data = lift(p.value, q.value, standard.value, unknown.value, supply.value, galvanometer.value) do pv, qv, rv, rxv, ev, rgv
        bridge_model(pv, qv, rv, rxv, ev, rgv)
    end

    hlines!(null_axis, [0.0], color = MUTED, linestyle = :dash)
    lines!(null_axis, lift(value -> value.standard_values, data), lift(value -> value.current_values, data), color = CYAN, linewidth = 2.8, label = "I_G(R)")
    scatter!(null_axis, lift(value -> [value.standard], data), lift(value -> [value.current_ua], data), color = PINK, markersize = 16, label = "当前状态")
    vlines!(null_axis, lift(value -> [value.balanced_standard], data), color = AMBER, linestyle = :dot, linewidth = 2.0, label = "理论平衡点")
    axislegend(null_axis, position = :rt, framevisible = false, labelsize = 9)

    values = (
        lift(value -> @sprintf("I_G = %+.3f μA", value.current_ua), data),
        lift(value -> @sprintf("U_BD = %+.3f μV", value.null_residual_uv), data),
        lift(value -> @sprintf("Rₓ,测 = %.3f Ω", value.inferred_unknown), data),
        lift(value -> @sprintf("相对偏差 = %+.3f%%", value.relative_error_percent), data),
    )
    detail = lift(data) do value
        @sprintf(
            "平衡时检流计支路 I_G=0，两个中点等势：EQ/(P+Q)=ERₓ/(R+Rₓ)，故 Rₓ=QR/P。\n当前 R平衡=%.3f Ω，开路戴维南电阻 R_th=%.2f Ω；换臂或换比率可检查接触电阻与桥臂系统差。",
            value.balanced_standard,
            value.detector.thevenin_resistance,
        )
    end
    add_metrics!(metrics, values, detail)
    bind_playback!(
        controls,
        7,
        standard,
        100:5:1000,
        [(p, 500), (q, 500), (standard, 470), (unknown, 470), (supply, 6.0), (galvanometer, 300)],
        step = 2,
    )
    return figure
end

function balance_model(p, q, indicated_standard, unknown, supply, galvanometer, dial_step, contact)
    all(value -> Float64(value) >= 0, (dial_step, contact)) ||
        throw(ArgumentError("步进值与接触电阻不能为负"))
    step = max(Float64(dial_step), eps())
    quantized_standard = round(Float64(indicated_standard) / step) * step
    effective_standard = quantized_standard + Float64(contact)
    base = bridge_model(p, q, effective_standard, unknown, supply, galvanometer)
    theoretical_indication = Float64(p) * Float64(unknown) / Float64(q) - Float64(contact)
    scan_half_width = max(20.0 * step, 0.08 * theoretical_indication)
    scan_values = collect(range(
        max(step, theoretical_indication - scan_half_width),
        theoretical_indication + scan_half_width;
        length = 241,
    ))
    scan_currents = [
        1.0e6 * detector_current(
            p,
            q,
            round(value / step) * step + Float64(contact),
            unknown,
            supply,
            galvanometer,
        ).current
        for value in scan_values
    ]
    inferred_indicated = Float64(q) * quantized_standard / Float64(p)
    inferred_corrected = Float64(q) * effective_standard / Float64(p)
    error_values = 100.0 .* (
        Float64(q) .* scan_values ./ Float64(p) .- Float64(unknown)
    ) ./ Float64(unknown)
    return (;
        base,
        quantized_standard,
        effective_standard,
        theoretical_indication,
        scan_values,
        scan_currents,
        error_values,
        inferred_indicated,
        inferred_corrected,
        uncorrected_error_percent =
            100.0 * (inferred_indicated - Float64(unknown)) / Float64(unknown),
        corrected_error_percent =
            100.0 * (inferred_corrected - Float64(unknown)) / Float64(unknown),
    )
end

function balance_figure()
    figure, controls, metrics = base_figure()
    current_axis = Axis(
        figure[1, 1],
        title = "粗调—细调：寻找检流计零点",
        xlabel = "电阻箱示值 R / Ω",
        ylabel = "I_G / μA",
    )
    error_axis = Axis(
        figure[1, 2],
        title = "示值分辨力与测量偏差",
        xlabel = "电阻箱示值 R / Ω",
        ylabel = "(Rₓ,测-Rₓ)/Rₓ / %",
    )

    p = add_slider!(controls, 1, "比例臂 P", 100:50:1000, 500, value -> @sprintf("%.0f Ω", value))
    q = add_slider!(controls, 2, "比例臂 Q", 100:50:1000, 500, value -> @sprintf("%.0f Ω", value))
    indicated = add_slider!(controls, 3, "电阻箱示值 R", 350:1:650, 470, value -> @sprintf("%.0f Ω", value))
    unknown = add_slider!(controls, 4, "真实 Rₓ", 350:1:650, 470, value -> @sprintf("%.0f Ω", value))
    dial_step = add_slider!(controls, 5, "最小步进 ΔR", 0.5:0.5:10.0, 1.0, value -> @sprintf("%.1f Ω", value))
    contact = add_slider!(controls, 6, "接触/引线电阻 r_c", 0.0:0.1:5.0, 0.8, value -> @sprintf("%.1f Ω", value))

    data = lift(p.value, q.value, indicated.value, unknown.value, dial_step.value, contact.value) do pv, qv, rv, rxv, stepv, rcv
        balance_model(pv, qv, rv, rxv, 6.0, 300.0, stepv, rcv)
    end

    hlines!(current_axis, [0.0], color = MUTED, linestyle = :dash)
    lines!(current_axis, lift(value -> value.scan_values, data), lift(value -> value.scan_currents, data), color = CYAN, linewidth = 2.8)
    scatter!(current_axis, lift(value -> [value.quantized_standard], data), lift(value -> [value.base.current_ua], data), color = PINK, markersize = 16)
    vlines!(current_axis, lift(value -> [value.theoretical_indication], data), color = AMBER, linestyle = :dot, linewidth = 2.0)

    hlines!(error_axis, [0.0], color = MUTED, linestyle = :dash)
    lines!(error_axis, lift(value -> value.scan_values, data), lift(value -> value.error_values, data), color = GREEN, linewidth = 2.8)
    scatter!(error_axis, lift(value -> [value.quantized_standard], data), lift(value -> [value.uncorrected_error_percent], data), color = AMBER, markersize = 16)

    values = (
        lift(value -> @sprintf("R量化 = %.2f Ω", value.quantized_standard), data),
        lift(value -> @sprintf("I_G = %+.3f μA", value.base.current_ua), data),
        lift(value -> @sprintf("Rₓ,示值 = %.3f Ω", value.inferred_indicated), data),
        lift(value -> @sprintf("接触修正 = %+.3f%%", value.corrected_error_percent), data),
    )
    detail = lift(data) do value
        @sprintf(
            "粗调时先断开检流计或串入保护电阻，逐步缩小 R 的步进；细调后再读取电阻箱。\n当前理论示值 %.3f Ω；若忽略 r_c，偏差 %+.3f%%，计入 r_c 后偏差 %+.3f%%。",
            value.theoretical_indication,
            value.uncorrected_error_percent,
            value.corrected_error_percent,
        )
    end
    add_metrics!(metrics, values, detail)
    bind_playback!(
        controls,
        7,
        indicated,
        350:1:650,
        [(p, 500), (q, 500), (indicated, 470), (unknown, 470), (dial_step, 1.0), (contact, 0.8)],
        step = 2,
    )
    return figure
end

function sensitivity_model(p, q, unknown, supply, galvanometer, current_resolution_na, bridge_u_ppm)
    all(value -> Float64(value) > 0, (p, q, unknown, supply, galvanometer, current_resolution_na)) ||
        throw(ArgumentError("电阻、电压和电流分辨力必须大于零"))
    Float64(bridge_u_ppm) >= 0 || throw(ArgumentError("桥臂相对标准不确定度不能为负"))
    standard_balance = Float64(p) * Float64(unknown) / Float64(q)
    balance = detector_current(p, q, standard_balance, unknown, supply, galvanometer)
    derivative_voltage = abs(
        Float64(supply) * standard_balance / (standard_balance + Float64(unknown))^2
    )
    current_sensitivity = derivative_voltage / (
        Float64(galvanometer) + balance.thevenin_resistance
    )
    mismatch_percent = collect(range(-2.0, 2.0; length = 241))
    trial_unknowns = Float64(unknown) .* (1.0 .+ mismatch_percent ./ 100.0)
    selected_currents = [
        1.0e6 * detector_current(
            p,
            q,
            standard_balance,
            trial,
            supply,
            galvanometer,
        ).current
        for trial in trial_unknowns
    ]
    low_currents = [
        1.0e6 * detector_current(
            p,
            q,
            standard_balance,
            trial,
            max(0.5, Float64(supply) / 2.0),
            galvanometer,
        ).current
        for trial in trial_unknowns
    ]
    null_uncertainty_ohm = Float64(current_resolution_na) * 1.0e-9 / current_sensitivity
    ratio_relative = Float64(bridge_u_ppm) * 1.0e-6
    standard_relative = 0.5 * ratio_relative
    null_relative = null_uncertainty_ohm / Float64(unknown)
    contact_relative = 0.10 / standard_balance
    component_labels = ["比例臂", "标准臂", "检流计", "接触"]
    component_percent = 100.0 .* [ratio_relative, standard_relative, null_relative, contact_relative]
    combined_relative = sqrt(
        ratio_relative^2 + standard_relative^2 + null_relative^2 + contact_relative^2
    )
    return (;
        standard_balance,
        balance,
        derivative_voltage,
        current_sensitivity,
        mismatch_percent,
        selected_currents,
        low_currents,
        null_uncertainty_ohm,
        component_labels,
        component_indices = collect(1:4),
        component_percent,
        combined_relative,
        expanded_uncertainty_ohm = 2.0 * Float64(unknown) * combined_relative,
    )
end

function sensitivity_figure()
    figure, controls, metrics = base_figure()
    sensitivity_axis = Axis(
        figure[1, 1],
        title = "零点附近检流计响应",
        xlabel = "Rₓ 偏离平衡值 / %",
        ylabel = "I_G / μA",
    )
    budget_axis = Axis(
        figure[1, 2],
        title = "相对标准不确定度预算",
        xlabel = "来源",
        ylabel = "相对分量 / %",
        xticks = (collect(1:4), ["P/Q", "R", "G", "接触"]),
    )

    p = add_slider!(controls, 1, "比例臂 P", 100:50:1000, 500, value -> @sprintf("%.0f Ω", value))
    q = add_slider!(controls, 2, "比例臂 Q", 100:50:1000, 500, value -> @sprintf("%.0f Ω", value))
    unknown = add_slider!(controls, 3, "待测电阻 Rₓ", 100:10:1000, 470, value -> @sprintf("%.0f Ω", value))
    supply = add_slider!(controls, 4, "电源电压 E", 1.0:0.5:12.0, 6.0, value -> @sprintf("%.1f V", value))
    galvanometer = add_slider!(controls, 5, "检流计内阻 R_G", 50:25:1000, 300, value -> @sprintf("%.0f Ω", value))
    resolution = add_slider!(controls, 6, "检流计分辨力", 1:1:50, 10, value -> @sprintf("%.0f nA", value))
    bridge_u = add_slider!(controls, 7, "桥臂 uᵣ", 20:10:500, 100, value -> @sprintf("%.0f ppm", value))

    data = lift(p.value, q.value, unknown.value, supply.value, galvanometer.value, resolution.value, bridge_u.value) do pv, qv, rxv, ev, rgv, iv, uv
        sensitivity_model(pv, qv, rxv, ev, rgv, iv, uv)
    end

    hlines!(sensitivity_axis, [0.0], color = MUTED, linestyle = :dash)
    lines!(sensitivity_axis, lift(value -> value.mismatch_percent, data), lift(value -> value.selected_currents, data), color = CYAN, linewidth = 2.8, label = "当前 E")
    lines!(sensitivity_axis, lift(value -> value.mismatch_percent, data), lift(value -> value.low_currents, data), color = VIOLET, linestyle = :dash, linewidth = 2.2, label = "E/2")
    axislegend(sensitivity_axis, position = :rb, framevisible = false, labelsize = 10)

    barplot!(budget_axis, lift(value -> value.component_indices, data), lift(value -> value.component_percent, data), color = [CYAN, PINK, AMBER, GREEN])

    values = (
        lift(value -> @sprintf("R平衡 = %.3f Ω", value.standard_balance), data),
        lift(value -> @sprintf("|dI_G/dRₓ| = %.3f μA/Ω", 1.0e6 * value.current_sensitivity), data),
        lift(value -> @sprintf("u_null(Rₓ) = %.4f Ω", value.null_uncertainty_ohm), data),
        lift(value -> @sprintf("U(k=2) = %.3f Ω", value.expanded_uncertainty_ohm), data),
    )
    detail = lift(data) do value
        @sprintf(
            "电压灵敏度 |dU_BD/dRₓ|=ER/(R+Rₓ)²；电流灵敏度还要除以 R_G+R_th。\n增大 E 可提高零点灵敏度，但必须检查桥臂自热；合成 uᵣ=%.4f%%，扩展不确定度按 k=2 给出。",
            100.0 * value.combined_relative,
        )
    end
    add_metrics!(metrics, values, detail)
    bind_playback!(
        controls,
        8,
        supply,
        1.0:0.5:12.0,
        [(p, 500), (q, 500), (unknown, 470), (supply, 6.0), (galvanometer, 300), (resolution, 10), (bridge_u, 100)],
    )
    return figure
end

function fit_model(unknown, count_value, ratio_span, dial_step, contact_offset, scatter_amplitude)
    true_unknown = Float64(unknown)
    count = clamp(round(Int, count_value), 4, 10)
    span = Float64(ratio_span)
    step = Float64(dial_step)
    contact = Float64(contact_offset)
    scatter = Float64(scatter_amplitude)
    true_unknown > 0 || throw(ArgumentError("待测电阻必须大于零"))
    span > 0 || throw(ArgumentError("比率跨度必须大于零"))
    step > 0 || throw(ArgumentError("电阻箱分辨力必须大于零"))
    all(value -> value >= 0, (contact, scatter)) ||
        throw(ArgumentError("接触偏置与散布不能为负"))
    ratios = collect(range(max(0.2, 1.0 - span), 1.0 + span; length = count))
    pattern = [-0.72, 0.46, -0.18, 0.61, -0.39, 0.27, -0.09, 0.52, -0.31, 0.14]
    ideal_standard = true_unknown .* ratios
    observed_standard = [
        round((value + contact + scatter * pattern[index]) / step) * step
        for (index, value) in enumerate(ideal_standard)
    ]
    fit = linear_fit(ratios, observed_standard)
    residual_milliohm = 1000.0 .* fit.residuals
    point_estimates = observed_standard ./ ratios
    return (;
        true_unknown,
        count,
        ratios,
        ideal_standard,
        observed_standard,
        fit,
        residual_milliohm,
        point_estimates,
        mean_point_estimate = sum(point_estimates) / count,
        fitted_unknown = fit.slope,
        fitted_contact = fit.intercept,
        relative_error_percent =
            100.0 * (fit.slope - true_unknown) / true_unknown,
        expanded_uncertainty = 2.0 * fit.slope_uncertainty,
    )
end

function fit_figure()
    figure, controls, metrics = base_figure()
    fit_axis = Axis(
        figure[1, 1],
        title = "多比率平衡：R = Rₓ(P/Q) + r₀",
        xlabel = "比例 P/Q",
        ylabel = "平衡电阻箱示值 R / Ω",
    )
    residual_axis = Axis(
        figure[1, 2],
        title = "拟合残差诊断",
        xlabel = "比例 P/Q",
        ylabel = "残差 / mΩ",
    )

    unknown = add_slider!(controls, 1, "真实 Rₓ", 100:5:1000, 470, value -> @sprintf("%.0f Ω", value))
    count = add_slider!(controls, 2, "平衡次数 n", 4:1:10, 8, value -> @sprintf("%.0f 次", value))
    span = add_slider!(controls, 3, "P/Q 跨度", 0.2:0.1:0.8, 0.6, value -> @sprintf("±%.1f", value))
    dial_step = add_slider!(controls, 4, "电阻箱分辨力", 0.01:0.01:0.20, 0.05, value -> @sprintf("%.2f Ω", value))
    contact = add_slider!(controls, 5, "公共接触偏置 r₀", 0.0:0.05:2.0, 0.5, value -> @sprintf("%.2f Ω", value))
    scatter = add_slider!(controls, 6, "零点散布幅度", 0.0:0.05:1.0, 0.25, value -> @sprintf("%.2f Ω", value))

    data = lift(unknown.value, count.value, span.value, dial_step.value, contact.value, scatter.value) do rxv, nv, sv, stepv, cv, scatterv
        fit_model(rxv, nv, sv, stepv, cv, scatterv)
    end

    scatter!(fit_axis, lift(value -> value.ratios, data), lift(value -> value.observed_standard, data), color = CYAN, markersize = 13, label = "平衡读数")
    lines!(fit_axis, lift(value -> value.ratios, data), lift(value -> value.fit.predicted, data), color = GREEN, linewidth = 2.8, label = "自由截距拟合")
    lines!(fit_axis, lift(value -> value.ratios, data), lift(value -> value.ideal_standard, data), color = AMBER, linestyle = :dash, linewidth = 2.0, label = "理想关系")
    axislegend(fit_axis, position = :lt, framevisible = false, labelsize = 9)

    hlines!(residual_axis, [0.0], color = MUTED, linestyle = :dash)
    scatter!(residual_axis, lift(value -> value.ratios, data), lift(value -> value.residual_milliohm, data), color = PINK, markersize = 13)
    lines!(residual_axis, lift(value -> value.ratios, data), lift(value -> value.residual_milliohm, data), color = VIOLET, linewidth = 1.8)

    values = (
        lift(value -> @sprintf("Rₓ,拟合 = %.3f Ω", value.fitted_unknown), data),
        lift(value -> @sprintf("r₀,拟合 = %+.3f Ω", value.fitted_contact), data),
        lift(value -> @sprintf("R² = %.6f", value.fit.r_squared), data),
        lift(value -> @sprintf("U(Rₓ), k=2 = %.3f Ω", value.expanded_uncertainty), data),
    )
    detail = lift(data) do value
        @sprintf(
            "在不同 P/Q 下重新调零，按 R=Rₓ(P/Q)+r₀ 作自由截距拟合；斜率估计 Rₓ，截距诊断公共串联偏置。\n逐点换算平均值 %.3f Ω；斜率相对偏差 %+.4f%%。残差结构可提示电阻箱非线性或未建模接触变化。",
            value.mean_point_estimate,
            value.relative_error_percent,
        )
    end
    add_metrics!(metrics, values, detail)
    bind_playback!(
        controls,
        7,
        count,
        4:1:10,
        [(unknown, 470), (count, 8), (span, 0.6), (dial_step, 0.05), (contact, 0.5), (scatter, 0.25)],
    )
    return figure
end

function run_self_test()
    balanced = bridge_model(500.0, 500.0, 470.0, 470.0, 6.0, 300.0)
    @assert abs(balanced.current_ua) < 1.0e-12
    @assert abs(balanced.null_residual_uv) < 1.0e-10
    @assert isapprox(balanced.inferred_unknown, 470.0; rtol = 1.0e-14)
    @assert isapprox(balanced.balanced_standard, 470.0; rtol = 1.0e-14)

    ratio_bridge = bridge_model(1000.0, 100.0, 4700.0, 470.0, 6.0, 300.0)
    @assert abs(ratio_bridge.current_ua) < 1.0e-12
    @assert isapprox(ratio_bridge.inferred_unknown, 470.0; rtol = 1.0e-14)

    adjusted = balance_model(500.0, 500.0, 469.0, 470.0, 6.0, 300.0, 1.0, 1.0)
    @assert isapprox(adjusted.effective_standard, 470.0; atol = 1.0e-12)
    @assert abs(adjusted.base.current_ua) < 1.0e-12
    @assert adjusted.uncorrected_error_percent < 0.0
    @assert abs(adjusted.corrected_error_percent) < 1.0e-12

    sensitivity = sensitivity_model(500.0, 500.0, 470.0, 6.0, 300.0, 10.0, 100.0)
    @assert sensitivity.current_sensitivity > 0.0
    @assert sensitivity.null_uncertainty_ohm > 0.0
    @assert sensitivity.combined_relative > 0.0
    @assert maximum(sensitivity.selected_currents) > 0.0
    @assert minimum(sensitivity.selected_currents) < 0.0

    exact_fit = fit_model(470.0, 8.0, 0.6, 1.0e-9, 0.0, 0.0)
    @assert isapprox(exact_fit.fitted_unknown, 470.0; rtol = 1.0e-10)
    @assert abs(exact_fit.fitted_contact) < 1.0e-8
    @assert exact_fit.fit.r_squared > 0.999999999
    biased_fit = fit_model(470.0, 8.0, 0.6, 0.05, 0.5, 0.25)
    @assert biased_fit.fitted_unknown > 0.0
    @assert biased_fit.fit.r_squared > 0.999
    @assert biased_fit.expanded_uncertainty >= 0.0

    for builder in (principle_figure, balance_figure, sensitivity_figure, fit_figure)
        @assert builder() isa Figure
    end
    @assert occursin(".wheatstone-bridge-lab", PAGE_STYLE)
    @assert occursin("pointerdown", CLIENT_STATUS_SCRIPT)
    @assert occursin("baseWinscale * layoutScale", CLIENT_STATUS_SCRIPT)
    @assert occursin("wheatstone-bridge-wgl-ready", CLIENT_STATUS_SCRIPT)
    @assert occursin("\\nWebGL 状态", CLIENT_STATUS_SCRIPT)
    @assert occursin("\\n页面地址", CLIENT_STATUS_SCRIPT)
    @assert occursin("\\n\" + event.filename", CLIENT_STATUS_SCRIPT)
    println("惠斯通电桥四个独立网页实验自检通过：桥路原理、平衡调节、灵敏度误差与多比率拟合均正常。")
end

const PAGE_STYLE = """
html, body { margin: 0; width: 100%; height: 100%; background: #0b0f14; color: #eef3f8; }
body { position: relative; overflow: hidden; font-family: 'Microsoft YaHei', 'Noto Sans CJK SC', sans-serif; }
.wheatstone-bridge-lab { position: absolute; left: 0; top: 0; width: $(FIGURE_WIDTH)px; height: $(FIGURE_HEIGHT)px;
    margin: 0; padding: 0; box-sizing: border-box; overflow: hidden; background: #0b0f14;
    transform-origin: 0 0; }
.wheatstone-bridge-diagnostic {
    position: fixed; left: 16px; right: 16px; bottom: 16px; z-index: 1002;
    display: none; padding: 10px 12px; color: #f7d7d7;
    background: rgba(64, 20, 28, .94); border: 1px solid rgba(255, 85, 105, .65);
    border-radius: 6px; font: 13px/1.5 ui-monospace, Consolas, monospace;
    white-space: pre-wrap;
}
.wheatstone-bridge-diagnostic.visible { display: block; }
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
        const page = document.querySelector(".wheatstone-bridge-lab");
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
        let box = document.getElementById("wheatstone-bridge-diagnostic");
        if (!box) {
            box = document.createElement("div");
            box.id = "wheatstone-bridge-diagnostic";
            box.className = "wheatstone-bridge-diagnostic";
            document.body.appendChild(box);
        }
        box.textContent = detail;
        box.classList.add("visible");
        send("wheatstone-bridge-wgl-failed", detail);
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
            send("wheatstone-bridge-wgl-ready", glStatus);
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
            DOM.div(figure; class = "wheatstone-bridge-lab"),
            DOM.script(CLIENT_STATUS_SCRIPT),
        )
    end
end

function index_app()
    links = [
        DOM.a(name; href = path, style = "color:#73d7cf;margin-right:24px")
        for (name, path) in (
            ("桥路原理与零电流平衡", "./principle"),
            ("粗调细调与平衡读数", "./balance"),
            ("灵敏度与不确定度", "./sensitivity"),
            ("多比率测量与线性拟合", "./fit"),
        )
    ]
    return Bonito.App(
        DOM.div(
            DOM.style(PAGE_STYLE),
            DOM.h1("惠斯通电桥测电阻"),
            DOM.div(links...),
            style = "padding:32px;background:#0b0f14;color:#eef3f8;min-height:100vh",
        );
        title = "惠斯通电桥测电阻",
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
    host = get(ENV, "WHEATSTONE_BRIDGE_WEB_HOST", "127.0.0.1")
    port = parse(Int, get(ENV, "WHEATSTONE_BRIDGE_WEB_PORT", "9396"))
    proxy_url = strip(get(ENV, "WHEATSTONE_BRIDGE_WEB_PROXY_URL", "."))
    isempty(proxy_url) && (proxy_url = ".")
    server = Bonito.Server(host, port; proxy_url = proxy_url)
    Bonito.route!(server, "/__physics_health__" => health_app())
    Bonito.route!(server, "/" => index_app())
    Bonito.route!(server, "/principle" => experiment_app("桥路原理与零电流平衡", principle_figure))
    Bonito.route!(server, "/balance" => experiment_app("粗调细调与平衡读数", balance_figure))
    Bonito.route!(server, "/sensitivity" => experiment_app("灵敏度与不确定度", sensitivity_figure))
    Bonito.route!(server, "/fit" => experiment_app("多比率测量与线性拟合", fit_figure))
    println("惠斯通电桥网页实验已启动：http://$(host):$(port)")
    wait(server)
end

if abspath(PROGRAM_FILE) == @__FILE__
    main()
end
