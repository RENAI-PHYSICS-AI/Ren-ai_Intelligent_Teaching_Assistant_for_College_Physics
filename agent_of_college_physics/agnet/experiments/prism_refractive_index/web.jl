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
const HEALTH_MARKER = "physics-experiment:prism-refractive-index"
const CJK_PROBE_TEXT = "三棱镜折射率测定分光计调节顶角最小偏向角色散不确定度"
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

wrap_angle_deg(angle) = mod(Float64(angle) + 180.0, 360.0) - 180.0

function refractive_index_from_minimum(apex_deg, deviation_deg)
    apex = deg2rad(Float64(apex_deg))
    deviation = deg2rad(Float64(deviation_deg))
    0.0 < apex < pi || throw(ArgumentError("三棱镜顶角必须在 0° 与 180° 之间"))
    return sin((apex + deviation) / 2.0) / sin(apex / 2.0)
end

function minimum_deviation_deg(apex_deg, refractive_index)
    apex = deg2rad(Float64(apex_deg))
    n = Float64(refractive_index)
    argument = n * sin(apex / 2.0)
    0.0 < argument < 1.0 || throw(ArgumentError("该顶角和折射率组合不能形成透射的最小偏向位置"))
    return rad2deg(2.0 * asin(argument) - apex)
end

function collimation_model(slit_offset_mm, focal_length_mm, slit_width_mm, telescope_focus_mm, axis_tilt_arcmin, eye_shift_mm)
    f = Float64(focal_length_mm)
    f > 0 || throw(ArgumentError("准直物镜焦距必须大于零"))
    offset = Float64(slit_offset_mm)
    divergence_rad = atan(offset / f)
    axis_tilt_rad = deg2rad(Float64(axis_tilt_arcmin) / 60.0)
    total_slope = divergence_rad + axis_tilt_rad
    x = collect(range(0.0, 500.0; length = 160))
    half_width0 = max(Float64(slit_width_mm), 0.01) / 2.0
    upper = half_width0 .+ x .* tan(total_slope)
    lower = .-half_width0 .- x .* tan(total_slope)
    focus_error = Float64(telescope_focus_mm)
    blur_mm = hypot(Float64(slit_width_mm), 0.018 * abs(focus_error))
    parallax_arcmin = rad2deg(atan(Float64(eye_shift_mm) * focus_error / (f^2))) * 60.0
    quality = exp(-abs(offset) / 1.2 - abs(focus_error) / 10.0 - abs(axis_tilt_arcmin) / 25.0)
    return (; x, upper, lower, divergence_arcmin = rad2deg(divergence_rad) * 60.0,
            total_arcmin = rad2deg(total_slope) * 60.0, blur_mm, parallax_arcmin, quality,
            focus_error, eye_shift = Float64(eye_shift_mm))
end

function apex_model(true_apex_deg, table_zero_deg, least_count_arcmin, collimation_arcmin, repeat_count, repeat_noise_arcmin)
    apex = Float64(true_apex_deg)
    zero = Float64(table_zero_deg)
    least = Float64(least_count_arcmin)
    count = Int(round(repeat_count))
    count >= 3 || throw(ArgumentError("顶角测量至少重复三次"))
    pattern = [0.00, 0.61, -0.48, 0.29, -0.57, 0.42, -0.21, 0.53, -0.35, 0.18]
    collimation = Float64(collimation_arcmin) / 60.0
    theta1_exact = zero - apex
    theta2_exact = zero + apex
    quantize(value) = round(value * 60.0 / least) * least / 60.0
    readings1 = [quantize(theta1_exact + collimation / 2.0 + Float64(repeat_noise_arcmin) * pattern[mod1(i, length(pattern))] / 60.0) for i in 1:count]
    readings2 = [quantize(theta2_exact - collimation / 2.0 - Float64(repeat_noise_arcmin) * pattern[mod1(i + 3, length(pattern))] / 60.0) for i in 1:count]
    measured = abs.(readings2 .- readings1) ./ 2.0
    mean_apex = sum(measured) / count
    standard_deviation = count > 1 ? sqrt(sum(abs2, measured .- mean_apex) / (count - 1)) : 0.0
    standard_u = hypot(standard_deviation / sqrt(count), least / (60.0 * sqrt(12.0) * 2.0))
    ray_angles = deg2rad.([theta1_exact, theta2_exact])
    return (; apex, readings1, readings2, measured, mean_apex, standard_deviation, standard_u,
            reflection_separation = 2.0 * apex, ray_angles,
            residual_arcmin = (measured .- apex) .* 60.0)
end

function deviation_at_incidence(apex_deg, refractive_index, incidence_deg)
    apex = deg2rad(Float64(apex_deg))
    n = Float64(refractive_index)
    incidence = deg2rad(Float64(incidence_deg))
    r1 = asin(clamp(sin(incidence) / n, -1.0, 1.0))
    r2 = apex - r1
    emergence_argument = n * sin(r2)
    abs(emergence_argument) <= 1.0 || return NaN
    emergence = asin(emergence_argument)
    return rad2deg(incidence + emergence - apex)
end

function minimum_scan_model(apex_deg, refractive_index, incidence_offset_deg, scan_span_deg, slit_width_mm, least_count_arcmin)
    apex = Float64(apex_deg)
    n = Float64(refractive_index)
    dmin = minimum_deviation_deg(apex, n)
    symmetric_incidence = rad2deg(asin(n * sin(deg2rad(apex) / 2.0)))
    span = Float64(scan_span_deg)
    incidences = collect(range(max(0.1, symmetric_incidence - span), min(89.9, symmetric_incidence + span); length = 280))
    deviations = [deviation_at_incidence(apex, n, angle) for angle in incidences]
    valid = [isfinite(value) for value in deviations]
    incidences = incidences[valid]
    deviations = deviations[valid]
    current_incidence = clamp(symmetric_incidence + Float64(incidence_offset_deg), first(incidences), last(incidences))
    current_deviation = deviation_at_incidence(apex, n, current_incidence)
    observed_u_arcmin = hypot(Float64(least_count_arcmin) / sqrt(12.0), 0.35 * Float64(slit_width_mm))
    recovered_n = refractive_index_from_minimum(apex, dmin)
    return (; apex, n, dmin, symmetric_incidence, incidences, deviations,
            current_incidence, current_deviation, observed_u_arcmin, recovered_n,
            excess_arcmin = (current_deviation - dmin) * 60.0)
end

function cauchy_index(wavelength_nm, cauchy_a, cauchy_b_um2)
    wavelength_um = Float64(wavelength_nm) / 1000.0
    return Float64(cauchy_a) + Float64(cauchy_b_um2) / wavelength_um^2
end

function index_uncertainty(apex_deg, deviation_deg, u_apex_arcmin, u_deviation_arcmin)
    apex = deg2rad(Float64(apex_deg))
    deviation = deg2rad(Float64(deviation_deg))
    numerator = sin((apex + deviation) / 2.0)
    denominator = sin(apex / 2.0)
    dn_dd = 0.5 * cos((apex + deviation) / 2.0) / denominator
    dn_da = 0.5 * (cos((apex + deviation) / 2.0) * denominator - numerator * cos(apex / 2.0)) / denominator^2
    ua = deg2rad(Float64(u_apex_arcmin) / 60.0)
    ud = deg2rad(Float64(u_deviation_arcmin) / 60.0)
    return sqrt((dn_da * ua)^2 + (dn_dd * ud)^2)
end

function dispersion_model(apex_deg, cauchy_a, cauchy_b_um2, index_noise, u_apex_arcmin, u_deviation_arcmin)
    wavelengths = [404.656, 435.835, 486.133, 546.074, 587.562, 656.273, 706.519]
    labels = ["Hg h", "Hg g", "H F", "Hg e", "He d", "H C", "He r"]
    pattern = [0.00, 0.57, -0.44, 0.31, -0.62, 0.39, -0.21]
    true_indices = cauchy_index.(wavelengths, Float64(cauchy_a), Float64(cauchy_b_um2))
    measured_indices = true_indices .+ Float64(index_noise) .* pattern
    deviations = minimum_deviation_deg.(Float64(apex_deg), measured_indices)
    inverse_lambda2 = 1.0 ./ (wavelengths ./ 1000.0).^2
    fit = linear_fit(inverse_lambda2, measured_indices)
    curve_wavelengths = collect(range(400.0, 710.0; length = 260))
    curve_indices = fit.intercept .+ fit.slope ./ (curve_wavelengths ./ 1000.0).^2
    nd = fit.intercept + fit.slope / (0.587562^2)
    nF = fit.intercept + fit.slope / (0.486133^2)
    nC = fit.intercept + fit.slope / (0.656273^2)
    abbe = (nd - 1.0) / (nF - nC)
    individual_u = [index_uncertainty(apex_deg, deviation, u_apex_arcmin, u_deviation_arcmin) for deviation in deviations]
    combined_u = sqrt((sum(individual_u) / length(individual_u))^2 + (Float64(index_noise) / sqrt(3.0))^2)
    return (; wavelengths, labels, true_indices, measured_indices, deviations, inverse_lambda2, fit,
            curve_wavelengths, curve_indices, nd, nF, nC, abbe, individual_u, combined_u,
            expanded_u = 2.0 * combined_u, max_residual = maximum(abs.(fit.residuals)))
end

function collimation_figure()
    figure, controls, metrics = base_figure()
    ray_axis = Axis(figure[1, 1], title = "平行光调节与光束发散", xlabel = "离开准直物镜的距离 / mm", ylabel = "相对光轴高度 / mm")
    view_axis = Axis(figure[1, 2], title = "望远镜视场：消视差判据", xlabel = "横向位置 / mm", ylabel = "归一化亮度")
    slit_offset = add_slider!(controls, 1, "狭缝离焦", -3.0:0.1:3.0, 0.0, v -> @sprintf("%+.1f mm", v))
    focal_length = add_slider!(controls, 2, "准直镜焦距", 120:10:300, 200, v -> @sprintf("%.0f mm", v))
    slit_width = add_slider!(controls, 3, "狭缝宽度", 0.05:0.05:0.80, 0.20, v -> @sprintf("%.2f mm", v))
    telescope_focus = add_slider!(controls, 4, "望远镜离焦", -15:1:15, 0, v -> @sprintf("%+.0f mm", v))
    axis_tilt = add_slider!(controls, 5, "共轴倾斜", -30:2:30, 0, v -> @sprintf("%+.0f′", v))
    eye_shift = add_slider!(controls, 6, "眼睛横移", -8:1:8, 0, v -> @sprintf("%+.0f mm", v))
    data = lift(slit_offset.value, focal_length.value, slit_width.value, telescope_focus.value, axis_tilt.value, eye_shift.value) do a,b,c,d,e,f
        collimation_model(a,b,c,d,e,f)
    end
    band!(ray_axis, lift(v -> v.x, data), lift(v -> v.lower, data), lift(v -> v.upper, data), color = (CYAN, 0.25))
    lines!(ray_axis, lift(v -> v.x, data), lift(v -> v.upper, data), color = CYAN, linewidth = 2.2)
    lines!(ray_axis, lift(v -> v.x, data), lift(v -> v.lower, data), color = CYAN, linewidth = 2.2)
    hlines!(ray_axis, [0.0], color = MUTED, linestyle = :dash)
    view_x = collect(range(-2.0, 2.0; length = 220))
    brightness = lift(data) do v
        sigma = max(0.05, v.blur_mm)
        exp.(-0.5 .* ((view_x .- 0.04 * v.parallax_arcmin) ./ sigma).^2)
    end
    lines!(view_axis, view_x, brightness, color = AMBER, linewidth = 2.7)
    vlines!(view_axis, [0.0], color = PINK, linewidth = 1.8, label = "十字丝")
    axislegend(view_axis, position = :rt, framevisible = false, labelsize = 10)
    values = (
        lift(v -> @sprintf("发散角 = %+.2f′", v.divergence_arcmin), data),
        lift(v -> @sprintf("总偏斜 = %+.2f′", v.total_arcmin), data),
        lift(v -> @sprintf("像斑 = %.3f mm", v.blur_mm), data),
        lift(v -> @sprintf("调节质量 = %.1f%%", 100v.quality), data),
    )
    detail = lift(data) do v
        @sprintf("狭缝位于准直物镜焦平面时出射光近似平行；先调目镜使十字丝清晰，再调望远镜对无穷远，最后调准直管并消除视差。\n当前横移引起视差 %+.3f′；狭缝过宽只增加谱线宽度，不能代替正确合焦。", v.parallax_arcmin)
    end
    add_metrics!(metrics, values, detail)
    bind_playback!(controls, 7, slit_offset, -3.0:0.1:3.0, [(slit_offset,0.0),(focal_length,200),(slit_width,0.20),(telescope_focus,0),(axis_tilt,0),(eye_shift,0)]; step = 2)
    return figure
end

function apex_figure()
    figure, controls, metrics = base_figure()
    geometry_axis = Axis(figure[1, 1], title = "反射法测三棱镜顶角", xlabel = "x", ylabel = "y", aspect = DataAspect())
    residual_axis = Axis(figure[1, 2], title = "重复测量与残差", xlabel = "测量序号", ylabel = "A测-A真 / ′")
    apex = add_slider!(controls, 1, "棱镜真顶角", 45.0:0.5:75.0, 60.0, v -> @sprintf("%.1f°", v))
    table_zero = add_slider!(controls, 2, "转台零位", 90:2:270, 180, v -> @sprintf("%.0f°", v))
    least_count = add_slider!(controls, 3, "游标分度值", 0.5:0.5:5.0, 1.0, v -> @sprintf("%.1f′", v))
    collimation = add_slider!(controls, 4, "准直系统误差", -5.0:0.5:5.0, 0.0, v -> @sprintf("%+.1f′", v))
    repeats = add_slider!(controls, 5, "重复次数", 3:1:10, 6, v -> @sprintf("%.0f 次", v))
    repeat_noise = add_slider!(controls, 6, "瞄准散布", 0.0:0.2:4.0, 1.0, v -> @sprintf("%.1f′", v))
    data = lift(apex.value, table_zero.value, least_count.value, collimation.value, repeats.value, repeat_noise.value) do a,b,c,d,e,f
        apex_model(a,b,c,d,e,f)
    end
    prism_points = lift(data) do v
        a = deg2rad(v.apex / 2.0)
        [Point2f(0, 1.0), Point2f(-sin(a), -cos(a)), Point2f(sin(a), -cos(a))]
    end
    poly!(geometry_axis, prism_points, color = (VIOLET, 0.30), strokecolor = VIOLET, strokewidth = 2.5)
    for index in 1:2
        endpoints = lift(data) do v
            angle = v.ray_angles[index]
            [Point2f(0, 0), Point2f(1.35cos(angle), 1.35sin(angle))]
        end
        lines!(geometry_axis, endpoints, color = index == 1 ? CYAN : AMBER, linewidth = 3.0)
    end
    xlims!(geometry_axis, -1.5, 1.5); ylims!(geometry_axis, -1.35, 1.35); hidedecorations!(geometry_axis)
    scatter!(residual_axis, lift(v -> collect(eachindex(v.residual_arcmin)), data), lift(v -> v.residual_arcmin, data), color = PINK, markersize = 11)
    lines!(residual_axis, lift(v -> collect(eachindex(v.residual_arcmin)), data), lift(v -> v.residual_arcmin, data), color = PINK, linewidth = 1.8)
    hlines!(residual_axis, [0.0], color = MUTED, linestyle = :dash)
    values = (
        lift(v -> @sprintf("2A = %.4f°", v.reflection_separation), data),
        lift(v -> @sprintf("A测 = %.5f°", v.mean_apex), data),
        lift(v -> @sprintf("偏差 = %+.2f′", (v.mean_apex-v.apex)*60), data),
        lift(v -> @sprintf("u(A) = %.2f′", v.standard_u*60), data),
    )
    detail = lift(data) do v
        @sprintf("分别瞄准由两个工作面反射的狭缝像，若两望远镜读数差为 φ，则 A=φ/2；需使用同一游标并处理 0°/360° 跨界。\n当前 θ₁≈%.4f°，θ₂≈%.4f°；半差法同时削弱共同零点偏移。", v.readings1[1], v.readings2[1])
    end
    add_metrics!(metrics, values, detail)
    bind_playback!(controls, 7, apex, 45.0:0.5:75.0, [(apex,60.0),(table_zero,180),(least_count,1.0),(collimation,0.0),(repeats,6),(repeat_noise,1.0)])
    return figure
end

function minimum_deviation_figure()
    figure, controls, metrics = base_figure()
    scan_axis = Axis(figure[1, 1], title = "偏向角随入射角的转向点", xlabel = "入射角 i / °", ylabel = "偏向角 δ / °")
    ray_axis = Axis(figure[1, 2], title = "对称光路与最小偏向条件", xlabel = "x", ylabel = "y", aspect = DataAspect())
    apex = add_slider!(controls, 1, "棱镜顶角 A", 40.0:0.5:70.0, 60.0, v -> @sprintf("%.1f°", v))
    index = add_slider!(controls, 2, "折射率 n", 1.35:0.01:1.70, 1.52, v -> @sprintf("%.2f", v))
    incidence_offset = add_slider!(controls, 3, "离开对称位置", -8.0:0.2:8.0, 0.0, v -> @sprintf("%+.1f°", v))
    scan_span = add_slider!(controls, 4, "扫描半宽", 5:1:18, 12, v -> @sprintf("±%.0f°", v))
    slit_width = add_slider!(controls, 5, "狭缝像宽", 0.1:0.1:2.0, 0.5, v -> @sprintf("%.1f mm", v))
    least_count = add_slider!(controls, 6, "游标分度值", 0.5:0.5:5.0, 1.0, v -> @sprintf("%.1f′", v))
    data = lift(apex.value, index.value, incidence_offset.value, scan_span.value, slit_width.value, least_count.value) do a,b,c,d,e,f
        minimum_scan_model(a,b,c,d,e,f)
    end
    lines!(scan_axis, lift(v -> v.incidences, data), lift(v -> v.deviations, data), color = CYAN, linewidth = 2.8)
    scatter!(scan_axis, lift(v -> [v.current_incidence], data), lift(v -> [v.current_deviation], data), color = PINK, markersize = 13)
    hlines!(scan_axis, lift(v -> [v.dmin], data), color = AMBER, linestyle = :dash, linewidth = 1.8)
    prism_points = lift(data) do v
        a = deg2rad(v.apex / 2.0)
        [Point2f(0, 0.95), Point2f(-0.85sin(a), -0.85cos(a)), Point2f(0.85sin(a), -0.85cos(a))]
    end
    poly!(ray_axis, prism_points, color = (VIOLET, 0.30), strokecolor = VIOLET, strokewidth = 2.5)
    incident_ray = lift(data) do v
        angle = deg2rad(v.symmetric_incidence)
        [Point2f(-1.35cos(angle), -1.35sin(angle)), Point2f(-0.28, 0.0)]
    end
    emergent_ray = lift(data) do v
        angle = deg2rad(v.symmetric_incidence - v.dmin)
        [Point2f(0.28, 0.0), Point2f(0.28 + 1.2cos(angle), 1.2sin(angle))]
    end
    lines!(ray_axis, incident_ray, color = CYAN, linewidth = 3.0)
    lines!(ray_axis, [Point2f(-0.28,0), Point2f(0.28,0)], color = GREEN, linewidth = 3.0)
    lines!(ray_axis, emergent_ray, color = AMBER, linewidth = 3.0)
    xlims!(ray_axis, -1.6, 1.6); ylims!(ray_axis, -1.25, 1.25); hidedecorations!(ray_axis)
    values = (
        lift(v -> @sprintf("δmin = %.4f°", v.dmin), data),
        lift(v -> @sprintf("i对称 = %.4f°", v.symmetric_incidence), data),
        lift(v -> @sprintf("离极小值 = %.2f′", v.excess_arcmin), data),
        lift(v -> @sprintf("反演 n = %.6f", v.recovered_n), data),
    )
    detail = lift(data) do v
        @sprintf("最小偏向处光路关于棱镜对称：i₁=i₂，r₁=r₂=A/2，因此 n=sin[(A+δmin)/2]/sin(A/2)。\n实验中缓慢转动棱镜，谱线移动到转向点后反向；当前读数标准不确定度约 %.2f′。", v.observed_u_arcmin)
    end
    add_metrics!(metrics, values, detail)
    bind_playback!(controls, 7, incidence_offset, -8.0:0.2:8.0, [(apex,60.0),(index,1.52),(incidence_offset,0.0),(scan_span,12),(slit_width,0.5),(least_count,1.0)]; step = 2)
    return figure
end

function dispersion_figure()
    figure, controls, metrics = base_figure()
    spectrum_axis = Axis(figure[1, 1], title = "折射率色散与 Cauchy 拟合", xlabel = "波长 λ / nm", ylabel = "折射率 n")
    residual_axis = Axis(figure[1, 2], title = "拟合残差与测量不确定度", xlabel = "波长 λ / nm", ylabel = "n测-n拟 / 10⁻⁴")
    apex = add_slider!(controls, 1, "测得顶角 A", 55.0:0.2:65.0, 60.0, v -> @sprintf("%.1f°", v))
    cauchy_a = add_slider!(controls, 2, "Cauchy 常数 a", 1.45:0.005:1.60, 1.500, v -> @sprintf("%.3f", v))
    cauchy_b = add_slider!(controls, 3, "Cauchy 常数 b", 0.002:0.001:0.020, 0.008, v -> @sprintf("%.3f μm²", v))
    noise = add_slider!(controls, 4, "折射率散布", 0.0:0.0001:0.0010, 0.0002, v -> @sprintf("%.4f", v))
    u_apex = add_slider!(controls, 5, "顶角 u(A)", 0.2:0.2:3.0, 1.0, v -> @sprintf("%.1f′", v))
    u_deviation = add_slider!(controls, 6, "偏向角 u(δ)", 0.2:0.2:3.0, 1.0, v -> @sprintf("%.1f′", v))
    data = lift(apex.value, cauchy_a.value, cauchy_b.value, noise.value, u_apex.value, u_deviation.value) do a,b,c,d,e,f
        dispersion_model(a,b,c,d,e,f)
    end
    lines!(spectrum_axis, lift(v -> v.curve_wavelengths, data), lift(v -> v.curve_indices, data), color = CYAN, linewidth = 2.8, label = "Cauchy 拟合")
    scatter!(spectrum_axis, lift(v -> v.wavelengths, data), lift(v -> v.measured_indices, data), color = PINK, markersize = 11, label = "谱线测量")
    axislegend(spectrum_axis, position = :rt, framevisible = false, labelsize = 10)
    residuals_scaled = lift(data) do v
        1.0e4 .* (v.measured_indices .- (v.fit.intercept .+ v.fit.slope .* v.inverse_lambda2))
    end
    errorbars!(residual_axis, lift(v -> v.wavelengths, data), residuals_scaled,
               lift(v -> 1.0e4 .* v.individual_u, data), color = MUTED, whiskerwidth = 8)
    scatter!(residual_axis, lift(v -> v.wavelengths, data), residuals_scaled, color = AMBER, markersize = 10)
    hlines!(residual_axis, [0.0], color = MUTED, linestyle = :dash)
    values = (
        lift(v -> @sprintf("n_d = %.6f", v.nd), data),
        lift(v -> @sprintf("ν_d = %.2f", v.abbe), data),
        lift(v -> @sprintf("R² = %.6f", v.fit.r_squared), data),
        lift(v -> @sprintf("U(n) = %.1g", v.expanded_u), data),
    )
    detail = lift(data) do v
        @sprintf("可见区远离吸收带时可用 n(λ)=a+b/λ²；Abbe 数 νd=(nd-1)/(nF-nC) 描述主色散。\n逐条谱线先找各自的最小偏向位置，切勿保持棱镜不动只移动望远镜；当前最大拟合残差 %.2g。", v.max_residual)
    end
    add_metrics!(metrics, values, detail)
    bind_playback!(controls, 7, cauchy_b, 0.002:0.001:0.020, [(apex,60.0),(cauchy_a,1.500),(cauchy_b,0.008),(noise,0.0002),(u_apex,1.0),(u_deviation,1.0)])
    return figure
end

function run_self_test()
    @assert isapprox(minimum_deviation_deg(60.0, 1.5), 37.1807558; atol = 1.0e-6)
    @assert isapprox(refractive_index_from_minimum(60.0, minimum_deviation_deg(60.0, 1.5)), 1.5; atol = 1.0e-12)
    collimation = collimation_model(0.0, 200.0, 0.2, 0.0, 0.0, 0.0)
    @assert isapprox(collimation.divergence_arcmin, 0.0; atol = 1.0e-12)
    apex = apex_model(60.0, 180.0, 1.0, 0.0, 6, 0.0)
    @assert isapprox(apex.mean_apex, 60.0; atol = 1.0e-12)
    scan = minimum_scan_model(60.0, 1.52, 0.0, 12.0, 0.5, 1.0)
    @assert abs(scan.excess_arcmin) < 1.0e-8
    dispersion = dispersion_model(60.0, 1.5, 0.008, 0.0, 1.0, 1.0)
    @assert dispersion.fit.r_squared > 0.999999
    @assert dispersion.abbe > 20.0
    @assert dispersion.combined_u > 0.0
    for builder in (collimation_figure, apex_figure, minimum_deviation_figure, dispersion_figure)
        @assert builder() isa Figure
    end
    @assert occursin(".prism-refractive-index-lab", PAGE_STYLE)
    @assert occursin("pointerdown", CLIENT_STATUS_SCRIPT)
    @assert occursin("baseWinscale * layoutScale", CLIENT_STATUS_SCRIPT)
    @assert occursin("prism-refractive-index-wgl-ready", CLIENT_STATUS_SCRIPT)
    println("三棱镜折射率测定四个独立网页实验自检通过。")
end

const PAGE_STYLE = """
html, body { margin: 0; width: 100%; height: 100%; background: #0b0f14; color: #eef3f8; }
body { position: relative; overflow: hidden; font-family: 'Microsoft YaHei', 'Noto Sans CJK SC', sans-serif; }
.prism-refractive-index-lab { position: absolute; left: 0; top: 0; width: $(FIGURE_WIDTH)px; height: $(FIGURE_HEIGHT)px;
    margin: 0; padding: 0; box-sizing: border-box; overflow: hidden; background: #0b0f14; transform-origin: 0 0; }
.prism-refractive-index-diagnostic { position: fixed; left: 16px; right: 16px; bottom: 16px; z-index: 1002;
    display: none; padding: 10px 12px; color: #f7d7d7; background: rgba(64,20,28,.94);
    border: 1px solid rgba(255,85,105,.65); border-radius: 6px; font: 13px/1.5 ui-monospace,Consolas,monospace; white-space: pre-wrap; }
.prism-refractive-index-diagnostic.visible { display: block; }
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
        const page = document.querySelector(".prism-refractive-index-lab");
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
        let box = document.getElementById("prism-refractive-index-diagnostic");
        if (!box) { box = document.createElement("div"); box.id = "prism-refractive-index-diagnostic"; box.className = "prism-refractive-index-diagnostic"; document.body.appendChild(box); }
        box.textContent = detail; box.classList.add("visible"); send("prism-refractive-index-wgl-failed", detail);
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
        if (canvas && canvas.width > 0 && canvas.height > 0 && !spinnerVisible) { ready = true; send("prism-refractive-index-wgl-ready", glStatus); return; }
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
        DOM.div(DOM.style(PAGE_STYLE), DOM.div(builder(); class = "prism-refractive-index-lab"), DOM.script(CLIENT_STATUS_SCRIPT))
    end
end

function index_app()
    links = [DOM.a(name; href = path, style = "color:#73d7cf;margin-right:24px") for (name,path) in (
        ("分光计调节", "./collimation"),
        ("反射法测顶角", "./apex"),
        ("最小偏向角", "./minimum-deviation"),
        ("折射率、色散与不确定度", "./dispersion"),
    )]
    return Bonito.App(DOM.div(DOM.style(PAGE_STYLE), DOM.h1("三棱镜折射率测定"), DOM.div(links...),
        style = "padding:32px;background:#0b0f14;color:#eef3f8;min-height:100vh"); title = "三棱镜折射率测定")
end

health_app() = Bonito.App(DOM.pre(HEALTH_MARKER); title = HEALTH_MARKER)

function main()
    load_packaged_wgl_shaders!()
    WGLMakie.activate!(; use_html_widgets = true)
    configure_theme!()
    if "--self-test" in ARGS
        run_self_test(); return
    end
    host = get(ENV, "PRISM_REFRACTIVE_INDEX_WEB_HOST", "127.0.0.1")
    port = parse(Int, get(ENV, "PRISM_REFRACTIVE_INDEX_WEB_PORT", "9400"))
    proxy_url = strip(get(ENV, "PRISM_REFRACTIVE_INDEX_WEB_PROXY_URL", ".")); isempty(proxy_url) && (proxy_url = ".")
    server = Bonito.Server(host, port; proxy_url = proxy_url)
    Bonito.route!(server, "/__physics_health__" => health_app())
    Bonito.route!(server, "/" => index_app())
    Bonito.route!(server, "/collimation" => experiment_app("分光计调节", collimation_figure))
    Bonito.route!(server, "/apex" => experiment_app("反射法测顶角", apex_figure))
    Bonito.route!(server, "/minimum-deviation" => experiment_app("最小偏向角", minimum_deviation_figure))
    Bonito.route!(server, "/dispersion" => experiment_app("折射率、色散与不确定度", dispersion_figure))
    println("三棱镜折射率测定网页实验已启动：http://$(host):$(port)")
    wait(server)
end

if abspath(PROGRAM_FILE) == @__FILE__
    main()
end
