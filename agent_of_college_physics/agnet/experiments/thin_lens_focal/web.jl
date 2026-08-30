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
const CJK_PROBE_TEXT = "薄透镜焦距物距像距自准直共轭位移不确定度光具座"
const HEALTH_MARKER = "physics-experiment:thin-lens-focal"
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

function sample_mean(values)
    isempty(values) && throw(ArgumentError("样本不能为空"))
    return sum(Float64.(values)) / length(values)
end

function sample_std(values)
    length(values) >= 2 || throw(ArgumentError("标准差至少需要两个样本"))
    mean_value = sample_mean(values)
    return sqrt(sum(abs2, Float64.(values) .- mean_value) / (length(values) - 1))
end

thin_lens_focal(u, v) = Float64(u) * Float64(v) / (Float64(u) + Float64(v))
thin_lens_image_distance(u, f) = Float64(f) * Float64(u) / (Float64(u) - Float64(f))

function direct_model(object_distance_cm, true_focal_cm, principal_shift_mm, position_noise_mm, trial_count, object_height_cm)
    u_mount, focal = Float64(object_distance_cm), Float64(true_focal_cm)
    shift_cm = Float64(principal_shift_mm) / 10.0
    u_effective = u_mount + shift_cm
    u_effective > focal || throw(ArgumentError("物距必须大于焦距，才能在屏上得到实像"))
    v_effective = thin_lens_image_distance(u_effective, focal)
    v_mount = v_effective + shift_cm
    n = Int(round(trial_count))
    n >= 3 || throw(ArgumentError("重复测量次数至少为 3"))
    pattern_u = [0.00, 0.72, -0.55, 0.33, -0.41, 0.61, -0.26, 0.45, -0.67, 0.18]
    pattern_v = [0.31, -0.48, 0.65, -0.22, 0.00, 0.54, -0.37, 0.19, -0.59, 0.42]
    noise_cm = Float64(position_noise_mm) / 10.0
    measured_u = [u_mount + noise_cm * pattern_u[mod1(i, length(pattern_u))] for i in 1:n]
    measured_v = [v_mount + noise_cm * pattern_v[mod1(i, length(pattern_v))] for i in 1:n]
    focal_estimates = thin_lens_focal.(measured_u, measured_v)
    focal_mean = sample_mean(focal_estimates)
    focal_sem = sample_std(focal_estimates) / sqrt(n)
    magnification = -v_effective / u_effective
    image_height = Float64(object_height_cm) * magnification
    ray_x = [-u_effective, 0.0, v_effective]
    central_ray_y = [Float64(object_height_cm), 0.0, image_height]
    parallel_ray_y = [Float64(object_height_cm), Float64(object_height_cm), image_height]
    return (; u_mount, focal, shift_cm, u_effective, v_effective, v_mount, n, measured_u, measured_v,
            focal_estimates, focal_mean, focal_sem, magnification, image_height, ray_x, central_ray_y,
            parallel_ray_y, relative_error = (focal_mean - focal) / focal * 100.0)
end

function autocollimation_model(offset_mm, true_focal_cm, mirror_gap_cm, mirror_tilt_mrad, focus_width_mm, object_height_cm)
    offset = Float64(offset_mm)
    focal = Float64(true_focal_cm)
    gap = Float64(mirror_gap_cm)
    tilt = Float64(mirror_tilt_mrad)
    width = Float64(focus_width_mm)
    width > 0 || throw(ArgumentError("判焦宽度必须大于零"))
    object_distance = focal + offset / 10.0
    object_distance > 0 || throw(ArgumentError("物镜间距必须大于零"))
    scan_offsets = collect(range(-12.0, 12.0; length = 241))
    sharpness = exp.(-0.5 .* (scan_offsets ./ width).^2)
    current_sharpness = exp(-0.5 * (offset / width)^2)
    returned_axial_shift_mm = 2.0 * offset
    returned_lateral_shift_mm = 0.02 * gap * tilt
    measured_focal = object_distance
    object_height = Float64(object_height_cm)
    x_object, x_lens, x_mirror = -object_distance, 0.0, gap
    ray_x = [x_object, x_lens, x_mirror, x_lens, x_object]
    outgoing_y = [object_height, 0.0, -gap * object_height / focal,
                  returned_lateral_shift_mm / 10.0, object_height + returned_lateral_shift_mm / 10.0]
    return (; offset, focal, gap, tilt, width, object_distance, scan_offsets, sharpness, current_sharpness,
            returned_axial_shift_mm, returned_lateral_shift_mm, measured_focal, ray_x, outgoing_y,
            focal_error_mm = 10.0 * (measured_focal - focal))
end

function displacement_model(screen_distance_cm, true_focal_cm, current_position_percent, position_noise_mm, ruler_zero_mm, object_height_cm)
    distance, focal = Float64(screen_distance_cm), Float64(true_focal_cm)
    distance > 4.0 * focal || throw(ArgumentError("贝塞尔法要求物屏距离 L>4f"))
    displacement = sqrt(distance^2 - 4.0 * distance * focal)
    first_position = (distance - displacement) / 2.0
    second_position = (distance + displacement) / 2.0
    zero_cm = Float64(ruler_zero_mm) / 10.0
    noise_cm = Float64(position_noise_mm) / 10.0
    measured_first = first_position + zero_cm + 0.37 * noise_cm
    measured_second = second_position + zero_cm - 0.52 * noise_cm
    measured_displacement = measured_second - measured_first
    measured_focal = (distance^2 - measured_displacement^2) / (4.0 * distance)
    positions = collect(range(0.0, distance; length = 300))
    focus_width = max(noise_cm, 0.08) * 2.2
    focus_quality = max.(exp.(-0.5 .* ((positions .- first_position) ./ focus_width).^2),
                         exp.(-0.5 .* ((positions .- second_position) ./ focus_width).^2))
    current_fraction = clamp(Float64(current_position_percent), 0.0, 100.0) / 100.0
    current = distance * current_fraction
    current_quality = max(exp(-0.5 * ((current - first_position) / focus_width)^2),
                          exp(-0.5 * ((current - second_position) / focus_width)^2))
    u1, u2 = first_position, second_position
    v1, v2 = distance - first_position, distance - second_position
    magnifications = [-v1 / u1, -v2 / u2]
    image_heights = Float64(object_height_cm) .* magnifications
    return (; distance, focal, displacement, first_position, second_position, measured_first,
            measured_second, measured_displacement, measured_focal, positions, focus_quality,
            current, current_fraction, current_quality, magnifications, image_heights,
            relative_error = (measured_focal - focal) / focal * 100.0)
end

function uncertainty_model(object_distance_cm, image_distance_cm, repetition_count, ruler_u_mm, focus_u_mm, alignment_u_mm)
    u, v = Float64(object_distance_cm), Float64(image_distance_cm)
    u > 0 && v > 0 || throw(ArgumentError("物距和像距必须为正"))
    n = Int(round(repetition_count))
    n >= 4 || throw(ArgumentError("重复测量次数至少为 4"))
    focal = thin_lens_focal(u, v)
    pattern_u = [0.00, 0.71, -0.49, 0.28, -0.63, 0.44, -0.21, 0.56, -0.36, 0.17, -0.53, 0.34]
    pattern_v = [0.32, -0.57, 0.46, -0.18, 0.62, -0.39, 0.00, 0.51, -0.27, 0.22, -0.48, 0.37]
    scatter_mm = sqrt(Float64(focus_u_mm)^2 + Float64(alignment_u_mm)^2)
    trials_u = [u + scatter_mm * pattern_u[mod1(i, length(pattern_u))] / 10.0 for i in 1:n]
    trials_v = [v + scatter_mm * pattern_v[mod1(i, length(pattern_v))] / 10.0 for i in 1:n]
    focal_estimates = thin_lens_focal.(trials_u, trials_v)
    focal_mean = sample_mean(focal_estimates)
    type_a = sample_std(focal_estimates) / sqrt(n)
    sensitivity_u = v^2 / (u + v)^2
    sensitivity_v = u^2 / (u + v)^2
    common_sensitivity = sqrt(sensitivity_u^2 + sensitivity_v^2)
    ruler_component = common_sensitivity * Float64(ruler_u_mm) / 10.0
    focus_component = common_sensitivity * Float64(focus_u_mm) / 10.0
    alignment_component = common_sensitivity * Float64(alignment_u_mm) / 10.0
    components = [type_a, ruler_component, focus_component, alignment_component]
    combined_u = sqrt(sum(abs2, components))
    expanded_u = 2.0 * combined_u
    labels = ["A类重复", "标尺", "判焦", "共轴"]
    return (; u, v, n, focal, focal_estimates, focal_mean, sensitivity_u, sensitivity_v,
            components, labels, combined_u, expanded_u, relative_expanded = expanded_u / focal * 100.0)
end

function direct_figure()
    figure, controls, metrics = base_figure()
    ray_axis = Axis(figure[1, 1], title = "物距—像距法光路", xlabel = "相对透镜主平面位置 / cm", ylabel = "高度 / cm")
    trial_axis = Axis(figure[1, 2], title = "重复测量的焦距结果", xlabel = "测量序号", ylabel = "f / cm")
    object_distance = add_slider!(controls, 1, "物距 u", 18:1:60, 30, v -> @sprintf("%.0f cm", v))
    focal = add_slider!(controls, 2, "真实焦距", 6.0:0.5:15.0, 10.0, v -> @sprintf("%.1f cm", v))
    principal_shift = add_slider!(controls, 3, "主平面偏移", -3.0:0.2:3.0, 0.0, v -> @sprintf("%+.1f mm", v))
    noise = add_slider!(controls, 4, "判焦/读数噪声", 0.0:0.1:2.0, 0.6, v -> @sprintf("%.1f mm", v))
    trials = add_slider!(controls, 5, "重复次数", 3:1:10, 6, v -> @sprintf("%.0f 次", v))
    object_height = add_slider!(controls, 6, "物高", 1.0:0.5:6.0, 3.0, v -> @sprintf("%.1f cm", v))
    data = lift(object_distance.value, focal.value, principal_shift.value, noise.value, trials.value, object_height.value) do a,b,c,d,e,f
        direct_model(a,b,c,d,e,f)
    end
    lines!(ray_axis, lift(v -> v.ray_x, data), lift(v -> v.central_ray_y, data), color = CYAN, linewidth = 2.5, label = "过光心")
    lines!(ray_axis, lift(v -> v.ray_x, data), lift(v -> v.parallel_ray_y, data), color = AMBER, linewidth = 2.3, label = "平行主轴")
    vlines!(ray_axis, [0.0], color = VIOLET, linewidth = 3.0, label = "薄透镜")
    hlines!(ray_axis, [0.0], color = MUTED, linewidth = 1.2)
    axislegend(ray_axis, position = :rt, framevisible = false, labelsize = 10)
    scatter!(trial_axis, lift(v -> collect(1:v.n), data), lift(v -> v.focal_estimates, data), color = PINK, markersize = 11)
    hlines!(trial_axis, lift(v -> [v.focal], data), color = GREEN, linestyle = :dash, linewidth = 2.0)
    lines!(trial_axis, lift(v -> collect(1:v.n), data), lift(v -> fill(v.focal_mean, v.n), data), color = AMBER, linewidth = 2.2)
    values = (
        lift(v -> @sprintf("v = %.2f cm", v.v_mount), data),
        lift(v -> @sprintf("m = %.3f", v.magnification), data),
        lift(v -> @sprintf("f̄ = %.3f cm", v.focal_mean), data),
        lift(v -> @sprintf("相对偏差 = %+.2f%%", v.relative_error), data),
    )
    detail = lift(data) do v
        @sprintf("薄透镜成像：1/f=1/u+1/v，因此 f=uv/(u+v)，横向放大率 m=-v/u。\n当前像高 %.2f cm；主平面偏移使从镜架刻线量得的 u、v 同时带系统差，重复测量只能压低随机分量。", v.image_height)
    end
    add_metrics!(metrics, values, detail)
    bind_playback!(controls, 7, object_distance, 18:1:60, [(object_distance,30),(focal,10.0),(principal_shift,0.0),(noise,0.6),(trials,6),(object_height,3.0)])
    return figure
end

function autocollimation_figure()
    figure, controls, metrics = base_figure()
    path_axis = Axis(figure[1, 1], title = "平面镜自准直往返光路", xlabel = "光轴位置 / cm", ylabel = "光线高度 / cm")
    focus_axis = Axis(figure[1, 2], title = "重合像判焦曲线", xlabel = "物面相对焦面偏移 Δ / mm", ylabel = "归一化清晰度")
    offset = add_slider!(controls, 1, "物面偏焦 Δ", -12.0:0.2:12.0, 0.0, v -> @sprintf("%+.1f mm", v))
    focal = add_slider!(controls, 2, "真实焦距", 6.0:0.5:15.0, 10.0, v -> @sprintf("%.1f cm", v))
    mirror_gap = add_slider!(controls, 3, "透镜—平面镜距", 4:1:20, 10, v -> @sprintf("%.0f cm", v))
    tilt = add_slider!(controls, 4, "平面镜倾角", -5.0:0.2:5.0, 0.0, v -> @sprintf("%+.1f mrad", v))
    width = add_slider!(controls, 5, "判焦曲线宽度", 0.5:0.1:3.0, 1.2, v -> @sprintf("%.1f mm", v))
    object_height = add_slider!(controls, 6, "物标高度", 0.5:0.5:4.0, 2.0, v -> @sprintf("%.1f cm", v))
    data = lift(offset.value, focal.value, mirror_gap.value, tilt.value, width.value, object_height.value) do a,b,c,d,e,f
        autocollimation_model(a,b,c,d,e,f)
    end
    lines!(path_axis, lift(v -> v.ray_x, data), lift(v -> v.outgoing_y, data), color = CYAN, linewidth = 2.6, label = "往返光线")
    vlines!(path_axis, [0.0], color = VIOLET, linewidth = 3.0, label = "透镜")
    vlines!(path_axis, lift(v -> [v.gap], data), color = AMBER, linewidth = 3.0, label = "平面镜")
    hlines!(path_axis, [0.0], color = MUTED, linewidth = 1.2)
    axislegend(path_axis, position = :rt, framevisible = false, labelsize = 10)
    lines!(focus_axis, lift(v -> v.scan_offsets, data), lift(v -> v.sharpness, data), color = GREEN, linewidth = 2.7)
    scatter!(focus_axis, lift(v -> [v.offset], data), lift(v -> [v.current_sharpness], data), color = PINK, markersize = 16)
    vlines!(focus_axis, [0.0], color = AMBER, linestyle = :dash, linewidth = 1.8)
    values = (
        lift(v -> @sprintf("清晰度 = %.3f", v.current_sharpness), data),
        lift(v -> @sprintf("f测 = %.3f cm", v.measured_focal), data),
        lift(v -> @sprintf("轴向复像差 = %+.2f mm", v.returned_axial_shift_mm), data),
        lift(v -> @sprintf("横向错位 = %+.3f mm", v.returned_lateral_shift_mm), data),
    )
    detail = lift(data) do v
        @sprintf("物标位于前焦面时，出射光准直；经平面镜反射后原路返回，并在物面形成等大倒像。故物标—透镜距离给出 f。\n双程使轴向偏焦近似放大为 2Δ；平面镜倾斜主要造成横向错位，不能把“像出现”误当作“像已重合”。")
    end
    add_metrics!(metrics, values, detail)
    bind_playback!(controls, 7, offset, -12.0:0.2:12.0, [(offset,0.0),(focal,10.0),(mirror_gap,10),(tilt,0.0),(width,1.2),(object_height,2.0)]; step = 2)
    return figure
end

function displacement_figure()
    figure, controls, metrics = base_figure()
    focus_axis = Axis(figure[1, 1], title = "固定物屏距离下的两次清晰位置", xlabel = "透镜位置 x / cm", ylabel = "归一化清晰度")
    image_axis = Axis(figure[1, 2], title = "两共轭位置的像", xlabel = "透镜位置序号", ylabel = "像高 / cm", xticks = (1:2, ["位置 1", "位置 2"]))
    distance = add_slider!(controls, 1, "物屏距离 L", 80:2:140, 100, v -> @sprintf("%.0f cm", v))
    focal = add_slider!(controls, 2, "真实焦距", 8.0:0.5:18.0, 15.0, v -> @sprintf("%.1f cm", v))
    current = add_slider!(controls, 3, "透镜位置进度", 0:1:100, 18, v -> @sprintf("%.0f%%", v))
    noise = add_slider!(controls, 4, "位置判读噪声", 0.1:0.1:2.0, 0.6, v -> @sprintf("%.1f mm", v))
    zero = add_slider!(controls, 5, "标尺零点偏移", -5.0:0.5:5.0, 1.0, v -> @sprintf("%+.1f mm", v))
    object_height = add_slider!(controls, 6, "物高", 1.0:0.5:6.0, 3.0, v -> @sprintf("%.1f cm", v))
    data = lift(distance.value, focal.value, current.value, noise.value, zero.value, object_height.value) do a,b,c,d,e,f
        displacement_model(a,b,c,d,e,f)
    end
    lines!(focus_axis, lift(v -> v.positions, data), lift(v -> v.focus_quality, data), color = CYAN, linewidth = 2.7)
    scatter!(focus_axis, lift(v -> [v.first_position, v.second_position], data), [1.0, 1.0], color = GREEN, markersize = 13)
    scatter!(focus_axis, lift(v -> [v.current], data), lift(v -> [v.current_quality], data), color = PINK, markersize = 16)
    vlines!(focus_axis, lift(v -> [v.first_position, v.second_position], data), color = AMBER, linestyle = :dash, linewidth = 1.5)
    barplot!(image_axis, 1:2, lift(v -> v.image_heights, data), color = [VIOLET, AMBER])
    hlines!(image_axis, [0.0], color = MUTED, linewidth = 1.2)
    values = (
        lift(v -> @sprintf("x₁ = %.2f cm", v.measured_first), data),
        lift(v -> @sprintf("x₂ = %.2f cm", v.measured_second), data),
        lift(v -> @sprintf("d = %.2f cm", v.measured_displacement), data),
        lift(v -> @sprintf("f = %.3f cm", v.measured_focal), data),
    )
    detail = lift(data) do v
        @sprintf("贝塞尔位移法：L>4f 时有两处清晰位置，间距 d=√(L²-4Lf)，所以 f=(L²-d²)/(4L)。\n当前透镜位置 x=%.1f cm；两位置放大率互为倒数（%.3f 与 %.3f）。同一标尺零点同时平移 x₁、x₂，会在差值 d 中相消。", v.current, v.magnifications[1], v.magnifications[2])
    end
    add_metrics!(metrics, values, detail)
    bind_playback!(controls, 7, current, 0:1:100, [(distance,100),(focal,15.0),(current,18),(noise,0.6),(zero,1.0),(object_height,3.0)]; step = 2)
    return figure
end

function uncertainty_figure()
    figure, controls, metrics = base_figure()
    repeat_axis = Axis(figure[1, 1], title = "焦距重复测量", xlabel = "测量序号", ylabel = "f / cm")
    budget_axis = Axis(figure[1, 2], title = "标准不确定度分量", xlabel = "分量", ylabel = "u(f) / cm", xticks = (1:4, ["A类", "标尺", "判焦", "共轴"]))
    object_distance = add_slider!(controls, 1, "物距 u", 20:1:60, 30, v -> @sprintf("%.0f cm", v))
    image_distance = add_slider!(controls, 2, "像距 v", 15:1:60, 30, v -> @sprintf("%.0f cm", v))
    repetitions = add_slider!(controls, 3, "重复次数", 4:1:12, 8, v -> @sprintf("%.0f 次", v))
    ruler_u = add_slider!(controls, 4, "标尺标准不确定度", 0.1:0.1:1.5, 0.5, v -> @sprintf("%.1f mm", v))
    focus_u = add_slider!(controls, 5, "判焦标准不确定度", 0.1:0.1:2.0, 0.8, v -> @sprintf("%.1f mm", v))
    alignment_u = add_slider!(controls, 6, "共轴标准不确定度", 0.0:0.1:1.5, 0.4, v -> @sprintf("%.1f mm", v))
    data = lift(object_distance.value, image_distance.value, repetitions.value, ruler_u.value, focus_u.value, alignment_u.value) do a,b,c,d,e,f
        uncertainty_model(a,b,c,d,e,f)
    end
    scatter!(repeat_axis, lift(v -> collect(1:v.n), data), lift(v -> v.focal_estimates, data), color = PINK, markersize = 11)
    lines!(repeat_axis, lift(v -> collect(1:v.n), data), lift(v -> fill(v.focal_mean, v.n), data), color = AMBER, linewidth = 2.2)
    hlines!(repeat_axis, lift(v -> [v.focal], data), color = GREEN, linestyle = :dash, linewidth = 1.8)
    barplot!(budget_axis, 1:4, lift(v -> v.components, data), color = [CYAN, GREEN, AMBER, VIOLET])
    values = (
        lift(v -> @sprintf("f̄ = %.3f cm", v.focal_mean), data),
        lift(v -> @sprintf("cᵤ = %.4f", v.sensitivity_u), data),
        lift(v -> @sprintf("uᶜ(f) = %.3f cm", v.combined_u), data),
        lift(v -> @sprintf("U(k=2) = %.3f cm", v.expanded_u), data),
    )
    detail = lift(data) do v
        @sprintf("f=uv/(u+v)，灵敏系数 cᵤ=v²/(u+v)²、cᵥ=u²/(u+v)²；无相关假设下按 GUM 方和合成。\n当前 U/f=%.2f%%（k=2）。记录中应区分重复性、标尺校准、判焦宽度、光具座共轴和主平面定义。", v.relative_expanded)
    end
    add_metrics!(metrics, values, detail)
    bind_playback!(controls, 7, object_distance, 20:1:60, [(object_distance,30),(image_distance,30),(repetitions,8),(ruler_u,0.5),(focus_u,0.8),(alignment_u,0.4)])
    return figure
end

function run_self_test()
    @assert isapprox(thin_lens_focal(30.0, 60.0), 20.0; atol = 1.0e-12)
    @assert isapprox(thin_lens_image_distance(30.0, 10.0), 15.0; atol = 1.0e-12)
    direct = direct_model(30.0, 10.0, 0.0, 0.0, 6, 3.0)
    @assert isapprox(direct.focal_mean, 10.0; atol = 1.0e-12)
    @assert isapprox(direct.magnification, -0.5; atol = 1.0e-12)
    autocollimation = autocollimation_model(0.0, 10.0, 10.0, 0.0, 1.2, 2.0)
    @assert isapprox(autocollimation.current_sharpness, 1.0; atol = 1.0e-12)
    @assert isapprox(autocollimation.measured_focal, 10.0; atol = 1.0e-12)
    displacement = displacement_model(100.0, 15.0, 20.0, 0.0, 0.0, 3.0)
    @assert isapprox(displacement.measured_focal, 15.0; atol = 1.0e-10)
    @assert isapprox(displacement.magnifications[1] * displacement.magnifications[2], 1.0; atol = 1.0e-10)
    @assert isapprox(displacement.current, 20.0; atol = 1.0e-12)
    @assert isapprox(displacement_model(80.0, 15.0, 100.0, 0.0, 0.0, 3.0).current, 80.0; atol = 1.0e-12)
    budget = uncertainty_model(30.0, 30.0, 8, 0.5, 0.8, 0.4)
    @assert budget.combined_u > 0.0
    @assert isapprox(budget.expanded_u, 2.0 * budget.combined_u; atol = 1.0e-12)
    for builder in (direct_figure, autocollimation_figure, displacement_figure, uncertainty_figure)
        @assert builder() isa Figure
    end
    @assert occursin(".thin-lens-focal-lab", PAGE_STYLE)
    @assert occursin("pointerdown", CLIENT_STATUS_SCRIPT)
    @assert occursin("baseWinscale * layoutScale", CLIENT_STATUS_SCRIPT)
    @assert occursin("thin-lens-focal-wgl-ready", CLIENT_STATUS_SCRIPT)
    println("薄透镜焦距测定四个独立网页实验自检通过。")
end

const PAGE_STYLE = """
html, body { margin: 0; width: 100%; height: 100%; background: #0b0f14; color: #eef3f8; }
body { position: relative; overflow: hidden; font-family: 'Microsoft YaHei', 'Noto Sans CJK SC', sans-serif; }
.thin-lens-focal-lab { position: absolute; left: 0; top: 0; width: $(FIGURE_WIDTH)px; height: $(FIGURE_HEIGHT)px;
    margin: 0; padding: 0; box-sizing: border-box; overflow: hidden; background: #0b0f14; transform-origin: 0 0; }
.thin-lens-focal-diagnostic { position: fixed; left: 16px; right: 16px; bottom: 16px; z-index: 1002;
    display: none; padding: 10px 12px; color: #f7d7d7; background: rgba(64,20,28,.94);
    border: 1px solid rgba(255,85,105,.65); border-radius: 6px; font: 13px/1.5 ui-monospace,Consolas,monospace; white-space: pre-wrap; }
.thin-lens-focal-diagnostic.visible { display: block; }
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
        const page = document.querySelector(".thin-lens-focal-lab");
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
        let box = document.getElementById("thin-lens-focal-diagnostic");
        if (!box) { box = document.createElement("div"); box.id = "thin-lens-focal-diagnostic"; box.className = "thin-lens-focal-diagnostic"; document.body.appendChild(box); }
        box.textContent = detail; box.classList.add("visible"); send("thin-lens-focal-wgl-failed", detail);
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
        if (canvas && canvas.width > 0 && canvas.height > 0 && !spinnerVisible) { ready = true; send("thin-lens-focal-wgl-ready", glStatus); return; }
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
        DOM.div(DOM.style(PAGE_STYLE), DOM.div(builder(); class = "thin-lens-focal-lab"), DOM.script(CLIENT_STATUS_SCRIPT))
    end
end

function index_app()
    links = [DOM.a(name; href = path, style = "color:#73d7cf;margin-right:24px") for (name,path) in (
        ("物距—像距直接法", "./direct"),
        ("平面镜自准直法", "./autocollimation"),
        ("贝塞尔共轭位移法", "./displacement"),
        ("重复测量与不确定度", "./uncertainty"),
    )]
    return Bonito.App(DOM.div(DOM.style(PAGE_STYLE), DOM.h1("薄透镜焦距的测定"), DOM.div(links...),
        style = "padding:32px;background:#0b0f14;color:#eef3f8;min-height:100vh"); title = "薄透镜焦距的测定")
end

health_app() = Bonito.App(DOM.pre(HEALTH_MARKER); title = HEALTH_MARKER)

function main()
    load_packaged_wgl_shaders!()
    WGLMakie.activate!(; use_html_widgets = true)
    configure_theme!()
    if "--self-test" in ARGS
        run_self_test(); return
    end
    host = get(ENV, "THIN_LENS_FOCAL_WEB_HOST", "127.0.0.1")
    port = parse(Int, get(ENV, "THIN_LENS_FOCAL_WEB_PORT", "9399"))
    proxy_url = strip(get(ENV, "THIN_LENS_FOCAL_WEB_PROXY_URL", ".")); isempty(proxy_url) && (proxy_url = ".")
    server = Bonito.Server(host, port; proxy_url = proxy_url)
    Bonito.route!(server, "/__physics_health__" => health_app())
    Bonito.route!(server, "/" => index_app())
    Bonito.route!(server, "/direct" => experiment_app("物距—像距直接法", direct_figure))
    Bonito.route!(server, "/autocollimation" => experiment_app("平面镜自准直法", autocollimation_figure))
    Bonito.route!(server, "/displacement" => experiment_app("贝塞尔共轭位移法", displacement_figure))
    Bonito.route!(server, "/uncertainty" => experiment_app("重复测量与不确定度", uncertainty_figure))
    println("薄透镜焦距测定网页实验已启动：http://$(host):$(port)")
    wait(server)
end

if abspath(PROGRAM_FILE) == @__FILE__
    main()
end
