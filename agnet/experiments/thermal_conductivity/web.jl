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
const CJK_PROBE_TEXT = "固体热传导系数傅里叶定律稳态圆盘良导体棒冷却修正线性拟合不确定度"
const HEALTH_MARKER = "physics-experiment:thermal-conductivity"
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

function steady_state_model(power_w, disc_diameter_mm, disc_thickness_mm, delta_t, rod_diameter_mm, rod_gradient_k_m, loss_percent)
    power = Float64(power_w)
    disc_diameter = Float64(disc_diameter_mm) * 1.0e-3
    disc_thickness = Float64(disc_thickness_mm) * 1.0e-3
    delta_temperature = Float64(delta_t)
    rod_diameter = Float64(rod_diameter_mm) * 1.0e-3
    rod_gradient = Float64(rod_gradient_k_m)
    loss_fraction = Float64(loss_percent) / 100.0
    power > 0 || throw(ArgumentError("加热功率必须大于零"))
    disc_diameter > 0 && disc_thickness > 0 && rod_diameter > 0 || throw(ArgumentError("试样尺寸必须大于零"))
    delta_temperature > 0 && rod_gradient > 0 || throw(ArgumentError("温差和温度梯度必须大于零"))
    0 <= loss_fraction < 1 || throw(ArgumentError("旁路热损失应位于 0% 到 100% 之间"))
    effective_power = power * (1.0 - loss_fraction)
    disc_area = pi * disc_diameter^2 / 4.0
    rod_area = pi * rod_diameter^2 / 4.0
    disc_k = effective_power * disc_thickness / (disc_area * delta_temperature)
    rod_k = effective_power / (rod_area * rod_gradient)
    disc_x = collect(range(0.0, disc_thickness * 1.0e3; length = 120))
    disc_temperature = 20.0 .+ delta_temperature .* (1.0 .- disc_x ./ maximum(disc_x))
    rod_x = collect(range(0.0, 0.12; length = 140))
    rod_temperature = 70.0 .- rod_gradient .* rod_x
    return (;
        power,
        effective_power,
        loss_fraction,
        disc_area,
        rod_area,
        disc_k,
        rod_k,
        disc_x,
        disc_temperature,
        rod_x_mm = rod_x .* 1.0e3,
        rod_temperature,
        disc_heat_flux = effective_power / disc_area,
        rod_heat_flux = effective_power / rod_area,
    )
end

function steady_state_figure()
    figure, controls, metrics = base_figure()
    disc_axis = Axis(
        figure[1, 1],
        title = "稳态圆盘法：一维温度场",
        xlabel = "厚度坐标 x / mm",
        ylabel = "温度 T / ℃",
    )
    rod_axis = Axis(
        figure[1, 2],
        title = "良导体棒法：轴向温度梯度",
        xlabel = "棒上位置 x / mm",
        ylabel = "温度 T / ℃",
    )

    power = add_slider!(controls, 1, "加热功率 P", 0.5:0.05:5.0, 2.0, value -> @sprintf("%.2f W", value))
    disc_diameter = add_slider!(controls, 2, "圆盘直径 D", 60:2:140, 100, value -> @sprintf("%.0f mm", value))
    disc_thickness = add_slider!(controls, 3, "圆盘厚度 b", 4.0:0.5:20.0, 10.0, value -> @sprintf("%.1f mm", value))
    delta_t = add_slider!(controls, 4, "圆盘温差 ΔT", 8:1:50, 25, value -> @sprintf("%.0f K", value))
    rod_diameter = add_slider!(controls, 5, "金属棒直径 d", 6:1:20, 12, value -> @sprintf("%.0f mm", value))
    rod_gradient = add_slider!(controls, 6, "棒温度梯度 |dT/dx|", 20:5:240, 80, value -> @sprintf("%.0f K/m", value))
    loss = add_slider!(controls, 7, "旁路热损失", 0:1:30, 8, value -> @sprintf("%.0f%%", value))

    data = lift(power.value, disc_diameter.value, disc_thickness.value, delta_t.value, rod_diameter.value, rod_gradient.value, loss.value) do p, dd, b, dt, dr, gradient, loss_percent
        steady_state_model(p, dd, b, dt, dr, gradient, loss_percent)
    end
    lines!(disc_axis, lift(value -> value.disc_x, data), lift(value -> value.disc_temperature, data), color = CYAN, linewidth = 3)
    scatter!(disc_axis, lift(value -> [first(value.disc_x), last(value.disc_x)], data), lift(value -> [first(value.disc_temperature), last(value.disc_temperature)], data), color = AMBER, markersize = 14)
    lines!(rod_axis, lift(value -> value.rod_x_mm, data), lift(value -> value.rod_temperature, data), color = PINK, linewidth = 3)
    scatter!(rod_axis, lift(value -> value.rod_x_mm[1:20:end], data), lift(value -> value.rod_temperature[1:20:end], data), color = GREEN, markersize = 8)

    values = (
        lift(value -> @sprintf("λ圆盘 = %.4f W/(m·K)", value.disc_k), data),
        lift(value -> @sprintf("λ棒 = %.2f W/(m·K)", value.rod_k), data),
        lift(value -> @sprintf("q圆盘 = %.1f W/m²", value.disc_heat_flux), data),
        lift(value -> @sprintf("有效功率 = %.3f W", value.effective_power), data),
    )
    detail = lift(data) do value
        @sprintf("傅里叶定律 q=-λ∇T。圆盘法 λ=P有效 b/(AΔT)；良导体棒法 λ=P有效/[A|dT/dx|]。当前旁路修正 %.1f%%，两种几何强调面积、温差与梯度的独立测量。", 100.0 * value.loss_fraction)
    end
    add_metrics!(metrics, values, detail)
    bind_playback!(controls, 8, power, 0.5:0.05:5.0, [(power, 2.0), (disc_diameter, 100), (disc_thickness, 10.0), (delta_t, 25), (rod_diameter, 12), (rod_gradient, 80), (loss, 8)]; step = 2)
    return figure
end

function cooling_model(disc_mass_g, disc_specific_heat, specimen_diameter_mm, specimen_thickness_mm, hot_temperature, disc_temperature, cooling_rate_k_min, correction_percent; ambient = 20.0)
    mass = Float64(disc_mass_g) * 1.0e-3
    specific_heat = Float64(disc_specific_heat)
    diameter = Float64(specimen_diameter_mm) * 1.0e-3
    thickness = Float64(specimen_thickness_mm) * 1.0e-3
    hot = Float64(hot_temperature)
    disc = Float64(disc_temperature)
    rate_per_second = Float64(cooling_rate_k_min) / 60.0
    correction = Float64(correction_percent) / 100.0
    mass > 0 && specific_heat > 0 && diameter > 0 && thickness > 0 || throw(ArgumentError("质量、比热与尺寸必须大于零"))
    hot > disc > ambient || throw(ArgumentError("温度应满足 T热>T盘>T环境"))
    rate_per_second > 0 || throw(ArgumentError("冷却速率必须大于零"))
    area = pi * diameter^2 / 4.0
    base_heat_rate = mass * specific_heat * rate_per_second
    corrected_heat_rate = base_heat_rate * (1.0 + correction)
    conductivity = corrected_heat_rate * thickness / (area * (hot - disc))
    naive_conductivity = base_heat_rate * thickness / (area * (hot - disc))
    alpha = rate_per_second / (disc - ambient)
    times = collect(range(0.0, 900.0; length = 240))
    temperatures = ambient .+ (disc - ambient) .* exp.(-alpha .* times)
    tangent = disc .- rate_per_second .* times
    return (;
        area,
        base_heat_rate,
        corrected_heat_rate,
        conductivity,
        naive_conductivity,
        relative_correction = 100.0 * (conductivity - naive_conductivity) / naive_conductivity,
        times,
        temperatures,
        tangent,
        alpha,
        disc,
        ambient,
    )
end

function cooling_figure()
    figure, controls, metrics = base_figure()
    curve_axis = Axis(figure[1, 1], title = "Lees 圆盘冷却曲线与切线", xlabel = "冷却时间 t / s", ylabel = "金属盘温度 T / ℃")
    correction_axis = Axis(figure[1, 2], title = "冷却/边缘修正对 λ 的影响", xlabel = "修正比例 / %", ylabel = "热传导系数 λ / W·m⁻¹·K⁻¹")

    mass = add_slider!(controls, 1, "金属盘质量 m", 250:10:800, 500, value -> @sprintf("%.0f g", value))
    cp = add_slider!(controls, 2, "金属盘比热 c", 300:10:600, 385, value -> @sprintf("%.0f J/(kg·K)", value))
    diameter = add_slider!(controls, 3, "试样直径 D", 70:2:130, 100, value -> @sprintf("%.0f mm", value))
    thickness = add_slider!(controls, 4, "试样厚度 b", 2.0:0.5:15.0, 6.0, value -> @sprintf("%.1f mm", value))
    hot = add_slider!(controls, 5, "热端温度 T₁", 55:1:95, 80, value -> @sprintf("%.0f ℃", value))
    disc = add_slider!(controls, 6, "盘温 T₂", 30:1:55, 45, value -> @sprintf("%.0f ℃", value))
    rate = add_slider!(controls, 7, "同温冷却速率", 0.4:0.1:4.0, 1.6, value -> @sprintf("%.1f K/min", value))
    correction = add_slider!(controls, 8, "侧面/接触修正", 0:1:30, 10, value -> @sprintf("%.0f%%", value))

    data = lift(mass.value, cp.value, diameter.value, thickness.value, hot.value, disc.value, rate.value, correction.value) do m, c, d, b, t1, t2, r, corr
        cooling_model(m, c, d, b, t1, t2, r, corr)
    end
    lines!(curve_axis, lift(value -> value.times, data), lift(value -> value.temperatures, data), color = CYAN, linewidth = 3, label = "Newton 冷却曲线")
    lines!(curve_axis, lift(value -> value.times[1:70], data), lift(value -> value.tangent[1:70], data), color = AMBER, linestyle = :dash, linewidth = 2.2, label = "T₂ 处切线")
    axislegend(curve_axis, position = :rt, framevisible = false, labelsize = 10)
    correction_grid = collect(0.0:1.0:30.0)
    lines!(correction_axis, correction_grid, lift(value -> value.naive_conductivity .* (1.0 .+ correction_grid ./ 100.0), data), color = GREEN, linewidth = 3)
    scatter!(correction_axis, lift(value -> [value.relative_correction], data), lift(value -> [value.conductivity], data), color = PINK, markersize = 15)

    values = (
        lift(value -> @sprintf("λ修正 = %.4f W/(m·K)", value.conductivity), data),
        lift(value -> @sprintf("λ未修正 = %.4f W/(m·K)", value.naive_conductivity), data),
        lift(value -> @sprintf("P散 = %.3f W", value.corrected_heat_rate), data),
        lift(value -> @sprintf("冷却常数 α = %.5f s⁻¹", value.alpha), data),
    )
    detail = lift(data) do value
        @sprintf("稳态穿过试样的热流用金属盘在同一温度 T₂ 处的冷却速率换算：P=mc|dT/dt|；再以侧面、辐射和接触项修正。当前修正使 λ 改变 %+.2f%%。", value.relative_correction)
    end
    add_metrics!(metrics, values, detail)
    bind_playback!(controls, 9, rate, 0.4:0.1:4.0, [(mass, 500), (cp, 385), (diameter, 100), (thickness, 6.0), (hot, 80), (disc, 45), (rate, 1.6), (correction, 10)])
    return figure
end

function fit_model(material_index, power_w, rod_diameter_mm, fit_length_mm, points_count, temperature_noise, loss_percent)
    conductivities = [16.0, 109.0, 205.0, 401.0]
    names = ["不锈钢", "黄铜", "铝", "铜"]
    index = clamp(round(Int, material_index), 1, length(conductivities))
    true_k = conductivities[index]
    power = Float64(power_w)
    diameter = Float64(rod_diameter_mm) * 1.0e-3
    fit_length = Float64(fit_length_mm) * 1.0e-3
    count = clamp(round(Int, points_count), 5, 15)
    noise = Float64(temperature_noise)
    loss_fraction = Float64(loss_percent) / 100.0
    power > 0 && diameter > 0 && fit_length > 0 || throw(ArgumentError("功率和试样尺寸必须大于零"))
    0 <= loss_fraction < 1 || throw(ArgumentError("热损失比例不合法"))
    area = pi * diameter^2 / 4.0
    effective_power = power * (1.0 - loss_fraction)
    gradient = effective_power / (true_k * area)
    positions = collect(range(0.0, fit_length; length = count))
    pattern = [0.00, 0.62, -0.45, 0.31, -0.57, 0.22, -0.13, 0.49, -0.36, 0.17, -0.28, 0.41, -0.19, 0.08, -0.05]
    ideal = 75.0 .- gradient .* positions
    observed = ideal .+ noise .* pattern[1:count]
    fit = linear_fit(positions, observed)
    fitted_k = effective_power / (area * abs(fit.slope))
    return (;
        material = names[index],
        true_k,
        fitted_k,
        area,
        effective_power,
        gradient,
        positions_mm = positions .* 1.0e3,
        ideal,
        observed,
        fitted = fit.predicted,
        residuals = fit.residuals,
        r_squared = fit.r_squared,
        slope_uncertainty = fit.slope_uncertainty,
        relative_error = 100.0 * (fitted_k - true_k) / true_k,
    )
end

function fit_figure()
    figure, controls, metrics = base_figure()
    fit_axis = Axis(figure[1, 1], title = "良导体棒温度—位置线性拟合", xlabel = "位置 x / mm", ylabel = "温度 T / ℃")
    residual_axis = Axis(figure[1, 2], title = "拟合残差诊断", xlabel = "位置 x / mm", ylabel = "残差 / K")

    material = add_slider!(controls, 1, "材料 1钢/2黄铜/3铝/4铜", 1:1:4, 3, value -> @sprintf("%.0f", value))
    power = add_slider!(controls, 2, "有效加热功率 P", 0.5:0.1:5.0, 2.0, value -> @sprintf("%.1f W", value))
    diameter = add_slider!(controls, 3, "棒直径 d", 8:1:20, 12, value -> @sprintf("%.0f mm", value))
    fit_length = add_slider!(controls, 4, "拟合区长度 L", 60:10:140, 100, value -> @sprintf("%.0f mm", value))
    points = add_slider!(controls, 5, "测温点数 n", 5:1:15, 9, value -> @sprintf("%.0f", value))
    noise = add_slider!(controls, 6, "温度读数噪声", 0.0:0.02:0.5, 0.12, value -> @sprintf("%.2f K", value))
    loss = add_slider!(controls, 7, "轴向散热修正", 0:1:25, 6, value -> @sprintf("%.0f%%", value))

    data = lift(material.value, power.value, diameter.value, fit_length.value, points.value, noise.value, loss.value) do m, p, d, l, n, e, loss_percent
        fit_model(m, p, d, l, n, e, loss_percent)
    end
    scatter!(fit_axis, lift(value -> value.positions_mm, data), lift(value -> value.observed, data), color = AMBER, markersize = 11, label = "测量点")
    lines!(fit_axis, lift(value -> value.positions_mm, data), lift(value -> value.fitted, data), color = CYAN, linewidth = 3, label = "最小二乘直线")
    axislegend(fit_axis, position = :rt, framevisible = false, labelsize = 10)
    hlines!(residual_axis, [0.0], color = MUTED, linestyle = :dash)
    scatter!(residual_axis, lift(value -> value.positions_mm, data), lift(value -> value.residuals, data), color = PINK, markersize = 11)

    values = (
        lift(value -> @sprintf("材料：%s", value.material), data),
        lift(value -> @sprintf("λ拟合 = %.2f W/(m·K)", value.fitted_k), data),
        lift(value -> @sprintf("R² = %.6f", value.r_squared), data),
        lift(value -> @sprintf("相对偏差 = %+.3f%%", value.relative_error), data),
    )
    detail = lift(data) do value
        @sprintf("对稳态区 T(x)=a+bx 作最小二乘拟合，λ=P有效/(A|b|)。当前斜率 |b|=%.3f K/m，斜率标准不确定度 %.3f K/m；残差图用于识别接触热阻、径向散热与非稳态。", abs(value.gradient), value.slope_uncertainty)
    end
    add_metrics!(metrics, values, detail)
    bind_playback!(controls, 8, power, 0.5:0.1:5.0, [(material, 3), (power, 2.0), (diameter, 12), (fit_length, 100), (points, 9), (noise, 0.12), (loss, 6)])
    return figure
end

function uncertainty_model(power_w, length_mm, diameter_mm, delta_t, u_power_percent, u_length_mm, u_diameter_mm, u_temperature_k, repeatability_percent)
    power = Float64(power_w)
    length_value = Float64(length_mm) * 1.0e-3
    diameter = Float64(diameter_mm) * 1.0e-3
    temperature_difference = Float64(delta_t)
    power > 0 && length_value > 0 && diameter > 0 && temperature_difference > 0 || throw(ArgumentError("测量量必须大于零"))
    area = pi * diameter^2 / 4.0
    conductivity = power * length_value / (area * temperature_difference)
    components = [
        Float64(u_power_percent),
        100.0 * Float64(u_length_mm) * 1.0e-3 / length_value,
        200.0 * Float64(u_diameter_mm) * 1.0e-3 / diameter,
        100.0 * sqrt(2.0) * Float64(u_temperature_k) / temperature_difference,
        Float64(repeatability_percent),
    ]
    combined_percent = sqrt(sum(abs2, components))
    expanded_percent = 2.0 * combined_percent
    delta_grid = collect(range(5.0, 60.0; length = 160))
    combined_grid = [sqrt(components[1]^2 + components[2]^2 + components[3]^2 + (100.0 * sqrt(2.0) * Float64(u_temperature_k) / dt)^2 + components[5]^2) for dt in delta_grid]
    return (;
        conductivity,
        components,
        labels = ["功率 P", "长度 L", "直径 d（×2）", "温差 ΔT", "A类重复性"],
        combined_percent,
        expanded_percent,
        standard_uncertainty = conductivity * combined_percent / 100.0,
        expanded_uncertainty = conductivity * expanded_percent / 100.0,
        delta_grid,
        combined_grid,
        temperature_difference,
    )
end

function uncertainty_figure()
    figure, controls, metrics = base_figure()
    budget_axis = Axis(figure[1, 1], title = "相对标准不确定度预算", xlabel = "输入量", ylabel = "相对贡献 / %", xticks = (1:5, ["P", "L", "d×2", "ΔT", "A类"]))
    sensitivity_axis = Axis(figure[1, 2], title = "温差选择与合成不确定度", xlabel = "工作温差 ΔT / K", ylabel = "uᵣ(λ) / %")

    power = add_slider!(controls, 1, "功率 P", 0.5:0.1:5.0, 2.0, value -> @sprintf("%.1f W", value))
    length_value = add_slider!(controls, 2, "导热长度 L", 5.0:0.5:30.0, 10.0, value -> @sprintf("%.1f mm", value))
    diameter = add_slider!(controls, 3, "直径 d", 60:2:140, 100, value -> @sprintf("%.0f mm", value))
    delta_t = add_slider!(controls, 4, "温差 ΔT", 5:1:60, 25, value -> @sprintf("%.0f K", value))
    u_power = add_slider!(controls, 5, "功率相对标准不确定度", 0.1:0.1:3.0, 0.5, value -> @sprintf("%.1f%%", value))
    u_length = add_slider!(controls, 6, "长度标准不确定度", 0.01:0.01:0.20, 0.05, value -> @sprintf("%.2f mm", value))
    u_diameter = add_slider!(controls, 7, "直径标准不确定度", 0.02:0.02:0.40, 0.10, value -> @sprintf("%.2f mm", value))
    u_temperature = add_slider!(controls, 8, "单点测温标准不确定度", 0.02:0.02:0.50, 0.10, value -> @sprintf("%.2f K", value))
    repeatability = add_slider!(controls, 9, "A类重复性", 0.1:0.1:3.0, 0.8, value -> @sprintf("%.1f%%", value))

    data = lift(power.value, length_value.value, diameter.value, delta_t.value, u_power.value, u_length.value, u_diameter.value, u_temperature.value, repeatability.value) do p, l, d, dt, up, ul, ud, ut, ur
        uncertainty_model(p, l, d, dt, up, ul, ud, ut, ur)
    end
    barplot!(budget_axis, 1:5, lift(value -> value.components, data), color = [CYAN, GREEN, AMBER, PINK, VIOLET])
    lines!(sensitivity_axis, lift(value -> value.delta_grid, data), lift(value -> value.combined_grid, data), color = CYAN, linewidth = 3)
    scatter!(sensitivity_axis, lift(value -> [value.temperature_difference], data), lift(value -> [value.combined_percent], data), color = AMBER, markersize = 15)

    values = (
        lift(value -> @sprintf("λ = %.4f W/(m·K)", value.conductivity), data),
        lift(value -> @sprintf("uᵣ = %.3f%%", value.combined_percent), data),
        lift(value -> @sprintf("U(k=2) = %.4f W/(m·K)", value.expanded_uncertainty), data),
        lift(value -> @sprintf("相对扩展 Uᵣ = %.3f%%", value.expanded_percent), data),
    )
    detail = lift(data) do value
        @sprintf("λ=4PL/(πd²ΔT)，独立输入量按灵敏系数平方和合成；直径项系数为 2，温差由两次测温合成。结果报告：λ=(%.4f ± %.4f) W/(m·K)，k=2。", value.conductivity, value.expanded_uncertainty)
    end
    add_metrics!(metrics, values, detail)
    bind_playback!(controls, 10, delta_t, 5:1:60, [(power, 2.0), (length_value, 10.0), (diameter, 100), (delta_t, 25), (u_power, 0.5), (u_length, 0.05), (u_diameter, 0.10), (u_temperature, 0.10), (repeatability, 0.8)])
    return figure
end

function run_self_test()
    steady = steady_state_model(2.0, 100.0, 10.0, 25.0, 12.0, 80.0, 8.0)
    @assert steady.disc_k > 0.0
    @assert steady.rod_k > steady.disc_k
    @assert isapprox(steady.effective_power, 1.84; rtol = 1.0e-12)

    cooled = cooling_model(500.0, 385.0, 100.0, 6.0, 80.0, 45.0, 1.6, 10.0)
    @assert cooled.conductivity > cooled.naive_conductivity > 0.0
    @assert isapprox(cooled.relative_correction, 10.0; rtol = 1.0e-12)
    @assert cooled.temperatures[end] < cooled.temperatures[1]

    fitted_exact = fit_model(4.0, 2.0, 12.0, 100.0, 9.0, 0.0, 6.0)
    @assert fitted_exact.material == "铜"
    @assert fitted_exact.r_squared > 0.999999999
    @assert isapprox(fitted_exact.fitted_k, fitted_exact.true_k; rtol = 1.0e-12)
    fitted_noisy = fit_model(3.0, 2.0, 12.0, 100.0, 12.0, 0.2, 6.0)
    @assert fitted_noisy.slope_uncertainty > 0.0
    @assert !isempty(fitted_noisy.residuals)

    budget = uncertainty_model(2.0, 10.0, 100.0, 25.0, 0.5, 0.05, 0.10, 0.10, 0.8)
    @assert budget.conductivity > 0.0
    @assert budget.expanded_percent > budget.combined_percent > 0.0
    @assert length(budget.components) == 5

    for builder in (steady_state_figure, cooling_figure, fit_figure, uncertainty_figure)
        @assert builder() isa Figure
    end
    @assert occursin(".thermal-conductivity-lab", PAGE_STYLE)
    @assert occursin("pointerdown", CLIENT_STATUS_SCRIPT)
    @assert occursin("baseWinscale * layoutScale", CLIENT_STATUS_SCRIPT)
    @assert occursin("thermal-conductivity-wgl-ready", CLIENT_STATUS_SCRIPT)
    @assert occursin("\\nWebGL 状态", CLIENT_STATUS_SCRIPT)
    @assert occursin("\\n页面地址", CLIENT_STATUS_SCRIPT)
    @assert occursin("\\n\" + event.filename", CLIENT_STATUS_SCRIPT)
    println("固体热传导系数四个独立网页实验自检通过：稳态法、冷却修正、线性拟合与不确定度均正常。")
end

const PAGE_STYLE = """
html, body { margin: 0; width: 100%; height: 100%; background: #0b0f14; color: #eef3f8; }
body { position: relative; overflow: hidden; font-family: 'Microsoft YaHei', 'Noto Sans CJK SC', sans-serif; }
.thermal-conductivity-lab { position: absolute; left: 0; top: 0; width: $(FIGURE_WIDTH)px; height: $(FIGURE_HEIGHT)px;
    margin: 0; padding: 0; box-sizing: border-box; overflow: hidden; background: #0b0f14;
    transform-origin: 0 0; }
.thermal-conductivity-diagnostic {
    position: fixed; left: 16px; right: 16px; bottom: 16px; z-index: 1002;
    display: none; padding: 10px 12px; color: #f7d7d7;
    background: rgba(64, 20, 28, .94); border: 1px solid rgba(255, 85, 105, .65);
    border-radius: 6px; font: 13px/1.5 ui-monospace, Consolas, monospace;
    white-space: pre-wrap;
}
.thermal-conductivity-diagnostic.visible { display: block; }
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
        const page = document.querySelector(".thermal-conductivity-lab");
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
        let box = document.getElementById("thermal-conductivity-diagnostic");
        if (!box) {
            box = document.createElement("div");
            box.id = "thermal-conductivity-diagnostic";
            box.className = "thermal-conductivity-diagnostic";
            document.body.appendChild(box);
        }
        box.textContent = detail;
        box.classList.add("visible");
        send("thermal-conductivity-wgl-failed", detail);
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
            send("thermal-conductivity-wgl-ready", glStatus);
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
            DOM.div(figure; class = "thermal-conductivity-lab"),
            DOM.script(CLIENT_STATUS_SCRIPT),
        )
    end
end

function index_app()
    links = [
        DOM.a(name; href = path, style = "color:#73d7cf;margin-right:24px")
        for (name, path) in (
            ("稳态圆盘法与良导体棒法", "./steady-state"),
            ("冷却曲线与热损失修正", "./cooling"),
            ("温度梯度线性拟合", "./fit"),
            ("测量不确定度预算", "./uncertainty"),
        )
    ]
    return Bonito.App(
        DOM.div(
            DOM.style(PAGE_STYLE),
            DOM.h1("固体热传导系数测定"),
            DOM.div(links...),
            style = "padding:32px;background:#0b0f14;color:#eef3f8;min-height:100vh",
        );
        title = "固体热传导系数测定",
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
    host = get(ENV, "THERMAL_CONDUCTIVITY_WEB_HOST", "127.0.0.1")
    port = parse(Int, get(ENV, "THERMAL_CONDUCTIVITY_WEB_PORT", "9401"))
    proxy_url = strip(get(ENV, "THERMAL_CONDUCTIVITY_WEB_PROXY_URL", "."))
    isempty(proxy_url) && (proxy_url = ".")
    server = Bonito.Server(host, port; proxy_url = proxy_url)
    Bonito.route!(server, "/__physics_health__" => health_app())
    Bonito.route!(server, "/" => index_app())
    Bonito.route!(server, "/steady-state" => experiment_app("稳态圆盘法与良导体棒法", steady_state_figure))
    Bonito.route!(server, "/cooling" => experiment_app("冷却曲线与热损失修正", cooling_figure))
    Bonito.route!(server, "/fit" => experiment_app("温度梯度线性拟合", fit_figure))
    Bonito.route!(server, "/uncertainty" => experiment_app("测量不确定度预算", uncertainty_figure))
    println("固体热传导系数网页实验已启动：http://$(host):$(port)")
    wait(server)
end

if abspath(PROGRAM_FILE) == @__FILE__
    main()
end
