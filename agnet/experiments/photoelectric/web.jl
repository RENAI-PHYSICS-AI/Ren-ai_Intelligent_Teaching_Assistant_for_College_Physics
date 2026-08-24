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

# 2019 SI defines h and e exactly.  Keeping the exact constants in the model
# makes the ideal h/e fit a useful regression test instead of a rounded target.
const PLANCK_CONSTANT = 6.626_070_15e-34
const ELEMENTARY_CHARGE = 1.602_176_634e-19
const SPEED_OF_LIGHT = 299_792_458.0
const H_OVER_E = PLANCK_CONSTANT / ELEMENTARY_CHARGE
const HC_EV_NM = PLANCK_CONSTANT * SPEED_OF_LIGHT / ELEMENTARY_CHARGE * 1.0e9
const MERCURY_WAVELENGTHS_NM = (577.0, 546.0, 436.0, 405.0, 365.0)

# The Makie canvas, browser wrapper and client-side fit all use this same
# logical size.  The last row has a real bottom safe area for CJK glyphs.
const FIGURE_WIDTH = 960
const FIGURE_HEIGHT = 760

const CYAN = RGBf(0.18, 0.78, 0.92)
const PINK = RGBf(0.94, 0.35, 0.50)
const AMBER = RGBf(1.00, 0.72, 0.24)
const GREEN = RGBf(0.36, 0.82, 0.55)
const VIOLET = RGBf(0.61, 0.48, 0.92)
const MUTED = RGBf(0.58, 0.62, 0.70)
const PANEL_BG = RGBf(0.075, 0.085, 0.105)
const CJK_PROBE_TEXT = "光电效应可视化实验"
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
        joinpath(
            Sys.BINDIR,
            "..",
            "share",
            "photoelectric",
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
        "未找到真正包含中文字形的字体。请重新执行安装流程，或通过 PHYSICS_CJK_FONT 指定 Noto Sans CJK SC 字体文件。",
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
    # Makie orders tuple padding as left, right, bottom, top.  The CJK axis
    # titles extend higher than Makie's nominal text bounds in WGLMakie, so a
    # dedicated top safe area prevents the first row from being clipped after
    # the browser scales the canvas into the embedded viewport.
    figure = Figure(size = (FIGURE_WIDTH, FIGURE_HEIGHT), figure_padding = (18, 18, 18, 30))
    controls = GridLayout()
    metrics = GridLayout()
    figure[2, 1:2] = controls
    figure[3, 1:2] = metrics
    rowsize!(figure.layout, 1, 390)
    rowsize!(figure.layout, 2, 180)
    rowsize!(figure.layout, 3, 110)
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
    rowsize!(grid, row, 24)
    rowgap!(grid, 4)
    return slider
end

function add_metrics!(grid, values, detail)
    for (column, value) in enumerate(values)
        Label(grid[1, column], value, halign = :left)
        colsize!(grid, column, Relative(0.25))
    end
    Label(grid[2, 1:4], detail, color = MUTED, halign = :left)
    rowsize!(grid, 1, 30)
    rowsize!(grid, 2, 48)
    rowgap!(grid, 8)
    return nothing
end

function linear_fit(x, y)
    @assert length(x) == length(y) && length(x) >= 2
    x_mean = sum(x) / length(x)
    y_mean = sum(y) / length(y)
    denominator = sum((value - x_mean)^2 for value in x)
    denominator > 0 || error("线性拟合的横坐标不能全部相同。")
    slope = sum(
        (x[index] - x_mean) * (y[index] - y_mean)
        for index in eachindex(x)
    ) / denominator
    intercept = y_mean - slope * x_mean
    return slope, intercept
end

photon_energy_ev(wavelength_nm) = HC_EV_NM / wavelength_nm
stopping_voltage(wavelength_nm, work_function_ev) = max(
    photon_energy_ev(wavelength_nm) - work_function_ev,
    0.0,
)

function iv_photo_current(voltage, stopping, saturation)
    stopping <= 0 && return 0.0
    voltage <= -stopping && return 0.0
    voltage >= 0 && return saturation
    return saturation * ((voltage + stopping) / stopping)^1.5
end

function iv_model(
    wavelength_nm,
    intensity_percent,
    work_function_ev,
    saturation_nanoamp,
    selected_voltage,
)
    photon_energy = photon_energy_ev(wavelength_nm)
    kinetic_energy = max(photon_energy - work_function_ev, 0.0)
    stopping = kinetic_energy
    active_saturation = saturation_nanoamp * intensity_percent / 100
    voltage = collect(range(-3.2, 2.2; length = 271))
    current = [
        iv_photo_current(value, stopping, active_saturation)
        for value in voltage
    ]
    family_levels = (0.35, 0.65, 1.00)
    family_curves = [
        Point2f.(
            voltage,
            [
                iv_photo_current(value, stopping, saturation_nanoamp * level)
                for value in voltage
            ],
        )
        for level in family_levels
    ]
    selected_current = iv_photo_current(
        selected_voltage,
        stopping,
        active_saturation,
    )
    return (;
        curve = Point2f.(voltage, current),
        family_curves,
        selected_point = Point2f[Point2f(selected_voltage, selected_current)],
        cutoff_line = stopping > 0 ? [-stopping] : Float64[],
        photon_energy,
        kinetic_energy,
        stopping,
        selected_current,
        active = kinetic_energy > 0,
    )
end

function iv_figure()
    figure, controls, metrics = base_figure()
    current_axis = Axis(
        figure[1, 1],
        title = "光电管伏安特性",
        xlabel = "阴极—阳极电压 U / V",
        ylabel = "光电流 I / nA",
    )
    intensity_axis = Axis(
        figure[1, 2],
        title = "光强改变电流，不移动遏止电压",
        xlabel = "阴极—阳极电压 U / V",
        ylabel = "光电流 I / nA",
    )

    wavelength = add_slider!(controls, 1, "入射波长 λ", 320:5:700, 405, value -> @sprintf("%.0f nm", value))
    intensity = add_slider!(controls, 2, "相对光强", 10:5:100, 80, value -> @sprintf("%.0f%%", value))
    work_function = add_slider!(controls, 3, "逸出功 φ", 1.80:0.02:3.00, 2.15, value -> @sprintf("%.2f eV", value))
    saturation = add_slider!(controls, 4, "100% 饱和电流", 20:2:120, 80, value -> @sprintf("%.0f nA", value))
    selected_voltage = add_slider!(controls, 5, "读数电压 U", -3.0:0.05:2.0, 0.50, value -> @sprintf("%+.2f V", value))

    data = lift(
        wavelength.value,
        intensity.value,
        work_function.value,
        saturation.value,
        selected_voltage.value,
    ) do lambda, level, phi, saturation_value, voltage
        iv_model(
            Float64(lambda),
            Float64(level),
            Float64(phi),
            Float64(saturation_value),
            Float64(voltage),
        )
    end

    lines!(current_axis, lift(value -> value.curve, data), color = CYAN, linewidth = 2.8)
    scatter!(current_axis, lift(value -> value.selected_point, data), color = AMBER, markersize = 15)
    vlines!(current_axis, lift(value -> value.cutoff_line, data), color = PINK, linestyle = :dash, linewidth = 2.0)
    hlines!(current_axis, [0.0], color = (:white, 0.22), linestyle = :dot)

    family_colors = (VIOLET, CYAN, GREEN)
    family_labels = ("35% 光强", "65% 光强", "100% 光强")
    for index in 1:3
        lines!(
            intensity_axis,
            lift(value -> value.family_curves[index], data),
            color = family_colors[index],
            linewidth = 2.4,
            label = family_labels[index],
        )
    end
    vlines!(intensity_axis, lift(value -> value.cutoff_line, data), color = PINK, linestyle = :dash, linewidth = 2.0)
    hlines!(intensity_axis, [0.0], color = (:white, 0.22), linestyle = :dot)
    axislegend(intensity_axis, position = :rb, framevisible = false)
    limits!(current_axis, -3.2, 2.2, -3.0, 124.0)
    limits!(intensity_axis, -3.2, 2.2, -3.0, 124.0)

    values = (
        lift(value -> @sprintf("hν = %.3f eV", value.photon_energy), data),
        lift(value -> @sprintf("Kmax = %.3f eV", value.kinetic_energy), data),
        lift(value -> value.active ? @sprintf("Uₛ = %.3f V", value.stopping) : "Uₛ = 无", data),
        lift(value -> @sprintf("I(U) = %.2f nA", value.selected_current), data),
    )
    detail = lift(data) do value
        value.active ?
            "同一频率下，光强只改变单位时间的光子数和光电流；三条曲线共享同一遏止电压。" :
            "当 hν ≤ φ 时不发生外光电效应；继续增强光强也不能让光电子逸出。"
    end
    add_metrics!(metrics, values, detail)
    return figure
end

function planck_model(work_function_ev, contact_potential, noise_millivolt, sample_count)
    master_frequency = [
        SPEED_OF_LIGHT / (wavelength_nm * 1.0e-9)
        for wavelength_nm in MERCURY_WAVELENGTHS_NM
    ]
    first_index = length(master_frequency) - sample_count + 1
    source_indices = collect(first_index:length(master_frequency))
    candidate_frequency = master_frequency[source_indices]
    ideal_candidate = H_OVER_E .* candidate_frequency .- work_function_ev
    active_indices = findall(value -> value > 0.02, ideal_candidate)
    frequency = candidate_frequency[active_indices]
    source_for_noise = source_indices[active_indices]
    ideal = ideal_candidate[active_indices]
    measured = [
        ideal[index] + contact_potential +
        noise_millivolt * 1.0e-3 * sin(1.93 * source_for_noise[index] + 0.31)
        for index in eachindex(ideal)
    ]
    scaled_frequency = frequency ./ 1.0e14
    slope_scaled, intercept = linear_fit(scaled_frequency, measured)
    fit_frequency = collect(range(5.0e14, 8.8e14; length = 160))
    fit_voltage = slope_scaled .* (fit_frequency ./ 1.0e14) .+ intercept
    predicted = slope_scaled .* scaled_frequency .+ intercept
    residual = measured .- predicted
    residual_stems = Point2f[]
    for (frequency_value, residual_value) in zip(frequency ./ 1.0e12, 1.0e3 .* residual)
        push!(residual_stems, Point2f(frequency_value, 0.0))
        push!(residual_stems, Point2f(frequency_value, residual_value))
        push!(residual_stems, Point2f(NaN, NaN))
    end
    h_over_e_estimate = slope_scaled / 1.0e14
    h_estimate = h_over_e_estimate * ELEMENTARY_CHARGE
    work_estimate = contact_potential - intercept
    threshold_frequency = work_estimate / h_over_e_estimate
    return (;
        points = Point2f.(frequency ./ 1.0e12, measured),
        fit_line = Point2f.(fit_frequency ./ 1.0e12, fit_voltage),
        residual_points = Point2f.(frequency ./ 1.0e12, 1.0e3 .* residual),
        residual_stems,
        h_over_e_estimate,
        h_estimate,
        work_estimate,
        threshold_frequency,
        point_count = length(frequency),
        relative_error = h_estimate / PLANCK_CONSTANT - 1,
    )
end

function planck_figure()
    figure, controls, metrics = base_figure()
    fit_axis = Axis(
        figure[1, 1],
        title = "遏止电压—频率线性拟合",
        xlabel = "入射频率 f / THz",
        ylabel = "测得遏止电压 Uₛ / V",
    )
    residual_axis = Axis(
        figure[1, 2],
        title = "拟合残差",
        xlabel = "入射频率 f / THz",
        ylabel = "残差 / mV",
    )

    work_function = add_slider!(controls, 1, "逸出功 φ", 1.80:0.02:2.90, 2.15, value -> @sprintf("%.2f eV", value))
    contact = add_slider!(controls, 2, "接触电势差", -0.30:0.01:0.30, 0.08, value -> @sprintf("%+.2f V", value))
    noise = add_slider!(controls, 3, "电压读数波动", 0:2:60, 12, value -> @sprintf("%.0f mV", value))
    count = add_slider!(controls, 4, "汞谱线测量数", 3:5, 5, value -> @sprintf("%.0f 组", value))

    data = lift(
        work_function.value,
        contact.value,
        noise.value,
        count.value,
    ) do phi, potential, scatter, point_count
        planck_model(
            Float64(phi),
            Float64(potential),
            Float64(scatter),
            Int(point_count),
        )
    end

    scatter!(fit_axis, lift(value -> value.points, data), color = CYAN, markersize = 10, label = "模拟测量")
    lines!(fit_axis, lift(value -> value.fit_line, data), color = GREEN, linewidth = 2.7, label = "自由截距拟合")
    axislegend(fit_axis, position = :lt, framevisible = false)
    hlines!(residual_axis, [0.0], color = (:white, 0.30), linestyle = :dash)
    lines!(residual_axis, lift(value -> value.residual_stems, data), color = (CYAN, 0.58), linewidth = 2.0)
    scatter!(residual_axis, lift(value -> value.residual_points, data), color = CYAN, markersize = 9)
    limits!(fit_axis, 500.0, 880.0, -0.2, 2.2)
    limits!(residual_axis, 500.0, 880.0, -80.0, 80.0)

    values = (
        lift(value -> @sprintf("h = %.5g J·s", value.h_estimate), data),
        lift(value -> @sprintf("相对偏差 = %+.2f%%", 100 * value.relative_error), data),
        lift(value -> @sprintf("φ拟合 = %.3f eV", value.work_estimate), data),
        lift(value -> @sprintf("f₀ = %.1f THz", value.threshold_frequency / 1.0e12), data),
    )
    detail = lift(data) do value
        @sprintf(
            "使用 %d 个有效频点；斜率给出 h/e，截距同时含逸出功与接触电势差，二者不应混为普朗克常量。",
            value.point_count,
        )
    end
    add_metrics!(metrics, values, detail)
    return figure
end

function spectral_photocurrent_nanoamp(
    wavelength_nm,
    intensity_percent,
    work_function_ev,
    quantum_efficiency_percent,
    optical_power_microwatt,
)
    photon_energy = photon_energy_ev(wavelength_nm)
    excess = photon_energy - work_function_ev
    excess <= 0 && return 0.0
    photon_flux = optical_power_microwatt * 1.0e-6 / (
        photon_energy * ELEMENTARY_CHARGE
    )
    threshold_factor = sqrt(excess / photon_energy)
    electron_rate = photon_flux * intensity_percent / 100 *
        quantum_efficiency_percent / 100 * threshold_factor
    return ELEMENTARY_CHARGE * electron_rate * 1.0e9
end

function threshold_model(
    wavelength_nm,
    intensity_percent,
    work_function_ev,
    quantum_efficiency_percent,
    optical_power_microwatt,
)
    photon_energy = photon_energy_ev(wavelength_nm)
    kinetic_energy = max(photon_energy - work_function_ev, 0.0)
    red_limit = HC_EV_NM / work_function_ev
    current = spectral_photocurrent_nanoamp(
        wavelength_nm,
        intensity_percent,
        work_function_ev,
        quantum_efficiency_percent,
        optical_power_microwatt,
    )
    electron_rate = current * 1.0e-9 / ELEMENTARY_CHARGE
    wavelength_scan = collect(range(280.0, 750.0; length = 330))
    family_levels = (35.0, 65.0, 100.0)
    spectral_curves = [
        Point2f.(
            wavelength_scan,
            [
                spectral_photocurrent_nanoamp(
                    lambda,
                    level,
                    work_function_ev,
                    quantum_efficiency_percent,
                    optical_power_microwatt,
                )
                for lambda in wavelength_scan
            ],
        )
        for level in family_levels
    ]
    intensity_scan = collect(range(0.0, 100.0; length = 101))
    energy_curve = Point2f.(intensity_scan, fill(kinetic_energy, length(intensity_scan)))
    return (;
        spectral_curves,
        energy_curve,
        selected_energy = Point2f[Point2f(intensity_percent, kinetic_energy)],
        red_limit_line = [red_limit],
        photon_energy,
        kinetic_energy,
        red_limit,
        current,
        electron_rate,
        active = kinetic_energy > 0,
    )
end

function threshold_figure()
    figure, controls, metrics = base_figure()
    spectrum_axis = Axis(
        figure[1, 1],
        title = "红限与简化光谱响应",
        xlabel = "入射波长 λ / nm",
        ylabel = "光电流 I / nA",
    )
    energy_axis = Axis(
        figure[1, 2],
        title = "最大初动能与光强",
        xlabel = "相对光强 / %",
        ylabel = "Kmax / eV",
    )

    wavelength = add_slider!(controls, 1, "入射波长 λ", 300:5:720, 405, value -> @sprintf("%.0f nm", value))
    intensity = add_slider!(controls, 2, "相对光强", 5:5:100, 70, value -> @sprintf("%.0f%%", value))
    work_function = add_slider!(controls, 3, "逸出功 φ", 1.80:0.02:3.00, 2.15, value -> @sprintf("%.2f eV", value))
    efficiency = add_slider!(controls, 4, "量子效率", 0.5:0.1:8.0, 2.0, value -> @sprintf("%.1f%%", value))
    power = add_slider!(controls, 5, "100% 入射光功率", 0.2:0.1:5.0, 1.0, value -> @sprintf("%.1f μW", value))

    data = lift(
        wavelength.value,
        intensity.value,
        work_function.value,
        efficiency.value,
        power.value,
    ) do lambda, level, phi, quantum_efficiency, optical_power
        threshold_model(
            Float64(lambda),
            Float64(level),
            Float64(phi),
            Float64(quantum_efficiency),
            Float64(optical_power),
        )
    end

    family_colors = (VIOLET, CYAN, GREEN)
    family_labels = ("35% 光强", "65% 光强", "100% 光强")
    for index in 1:3
        lines!(
            spectrum_axis,
            lift(value -> value.spectral_curves[index], data),
            color = family_colors[index],
            linewidth = 2.4,
            label = family_labels[index],
        )
    end
    vlines!(spectrum_axis, lift(value -> value.red_limit_line, data), color = PINK, linestyle = :dash, linewidth = 2.0)
    axislegend(spectrum_axis, position = :rt, framevisible = false)
    lines!(energy_axis, lift(value -> value.energy_curve, data), color = CYAN, linewidth = 2.8)
    scatter!(energy_axis, lift(value -> value.selected_energy, data), color = AMBER, markersize = 15)
    limits!(spectrum_axis, 280.0, 750.0, 0.0, 230.0)
    limits!(energy_axis, 0.0, 100.0, -0.05, 2.45)

    values = (
        lift(value -> @sprintf("λ₀ = %.1f nm", value.red_limit), data),
        lift(value -> @sprintf("Kmax = %.3f eV", value.kinetic_energy), data),
        lift(value -> @sprintf("I = %.2f nA", value.current), data),
        lift(value -> @sprintf("Ṅₑ = %.3g s⁻¹", value.electron_rate), data),
    )
    detail = lift(data) do value
        value.active ?
            "频率高于红限频率时，增强光强只增加光电子数；最大初动能仍由 hν-φ 决定。" :
            "当 λ ≥ λ₀ 时单个光子能量不足，即使增强光强也不会产生光电子。"
    end
    add_metrics!(metrics, values, detail)
    return figure
end

function threshold_crossing(x, y, level)
    y[1] >= level && return x[1]
    for index in 2:length(x)
        if y[index] >= level && y[index - 1] < level
            fraction = (level - y[index - 1]) /
                max(y[index] - y[index - 1], eps(Float64))
            return x[index - 1] + fraction * (x[index] - x[index - 1])
        end
    end
    return x[end]
end

function uncertainty_model(
    wavelength_nm,
    work_function_ev,
    contact_potential,
    dark_current_nanoamp,
    leakage_nanoamp_per_volt,
    noise_nanoamp,
)
    true_stopping = stopping_voltage(wavelength_nm, work_function_ev)
    observed_cutoff = -true_stopping + contact_potential
    saturation = 50.0
    voltage = collect(range(-3.0, 0.7; length = 371))
    scale = max(true_stopping + 0.25, 0.32)
    photo_current = [
        value <= observed_cutoff ? 0.0 :
        saturation * min(((value - observed_cutoff) / scale)^1.5, 1.0)
        for value in voltage
    ]
    background = dark_current_nanoamp .+ leakage_nanoamp_per_volt .* voltage
    deterministic_noise = [
        noise_nanoamp * (sin(9.7 * value + 0.4) + 0.35sin(21.1 * value - 0.2))
        for value in voltage
    ]
    measured = photo_current .+ background .+ deterministic_noise
    # A 6% current threshold is high enough that the selected classroom-scale
    # dark/leakage ranges cannot trigger a false crossing at the scan boundary.
    threshold = 0.06 * saturation
    raw_cutoff = threshold_crossing(voltage, measured, threshold)
    dark_cutoff = threshold_crossing(
        voltage,
        measured .- dark_current_nanoamp,
        threshold,
    )
    corrected_current = measured .- background
    transformed = max.(corrected_current, 0.0) .^ (2 / 3)
    fit_indices = findall(
        index -> 0.08saturation <= corrected_current[index] <= 0.45saturation,
        eachindex(voltage),
    )
    tangent_cutoff = if length(fit_indices) >= 3
        slope, intercept = linear_fit(voltage[fit_indices], transformed[fit_indices])
        -intercept / slope
    else
        threshold_crossing(voltage, corrected_current, threshold)
    end
    raw_estimate = -raw_cutoff
    dark_estimate = -dark_cutoff
    extrapolated_estimate = -tangent_cutoff
    corrected_estimate = -(tangent_cutoff - contact_potential)
    estimates = (
        raw_estimate,
        dark_estimate,
        extrapolated_estimate,
        corrected_estimate,
    )
    errors = [
        100 * (estimate / true_stopping - 1)
        for estimate in estimates
    ]
    error_stems = Point2f[]
    for (index, error_value) in enumerate(errors)
        push!(error_stems, Point2f(index, 0.0))
        push!(error_stems, Point2f(index, error_value))
        push!(error_stems, Point2f(NaN, NaN))
    end
    return (;
        measured_curve = Point2f.(voltage, measured),
        background_curve = Point2f.(voltage, background),
        true_cutoff_line = [observed_cutoff],
        raw_cutoff_line = [raw_cutoff],
        tangent_cutoff_line = [tangent_cutoff],
        error_points = Point2f.(1:4, errors),
        error_stems,
        true_stopping,
        observed_cutoff,
        raw_estimate,
        dark_estimate,
        extrapolated_estimate,
        corrected_estimate,
        corrected_error = errors[4],
    )
end

function uncertainty_figure()
    figure, controls, metrics = base_figure()
    current_axis = Axis(
        figure[1, 1],
        title = "遏止区伏安特性与本底",
        xlabel = "阴极—阳极电压 U / V",
        ylabel = "测得电流 I / nA",
    )
    error_axis = Axis(
        figure[1, 2],
        title = "不同遏止电压判读策略",
        xlabel = "判读方法",
        ylabel = "Uₛ 相对偏差 / %",
        xticks = (1:4, ["原始阈值", "扣暗电流", "外推", "综合修正"]),
        xticklabelrotation = pi / 10,
    )

    wavelength = add_slider!(controls, 1, "入射波长 λ", 320:5:500, 405, value -> @sprintf("%.0f nm", value))
    work_function = add_slider!(controls, 2, "逸出功 φ", 1.80:0.02:2.30, 2.15, value -> @sprintf("%.2f eV", value))
    contact = add_slider!(controls, 3, "接触电势差", -0.20:0.01:0.20, 0.08, value -> @sprintf("%+.2f V", value))
    dark = add_slider!(controls, 4, "暗电流", -1.0:0.1:1.0, 0.4, value -> @sprintf("%+.1f nA", value))
    leakage = add_slider!(controls, 5, "漏电斜率", -0.20:0.02:0.20, 0.10, value -> @sprintf("%+.2f nA/V", value))
    noise = add_slider!(controls, 6, "读数波动", 0.0:0.05:1.0, 0.20, value -> @sprintf("%.2f nA", value))

    data = lift(
        wavelength.value,
        work_function.value,
        contact.value,
        dark.value,
        leakage.value,
        noise.value,
    ) do lambda, phi, potential, dark_value, leakage_value, scatter
        uncertainty_model(
            Float64(lambda),
            Float64(phi),
            Float64(potential),
            Float64(dark_value),
            Float64(leakage_value),
            Float64(scatter),
        )
    end

    lines!(current_axis, lift(value -> value.measured_curve, data), color = CYAN, linewidth = 2.6, label = "测得电流")
    lines!(current_axis, lift(value -> value.background_curve, data), color = VIOLET, linewidth = 2.0, linestyle = :dash, label = "暗电流+漏电")
    vlines!(current_axis, lift(value -> value.true_cutoff_line, data), color = GREEN, linewidth = 2.0, linestyle = :dash, label = "观测截止点")
    vlines!(current_axis, lift(value -> value.raw_cutoff_line, data), color = PINK, linewidth = 1.8, linestyle = :dot, label = "原始阈值")
    vlines!(current_axis, lift(value -> value.tangent_cutoff_line, data), color = AMBER, linewidth = 1.8, label = "变换外推")
    axislegend(current_axis, position = :lt, framevisible = false)

    hlines!(error_axis, [0.0], color = (:white, 0.30), linestyle = :dash)
    lines!(error_axis, lift(value -> value.error_stems, data), color = (CYAN, 0.58), linewidth = 3.0)
    scatter!(error_axis, lift(value -> value.error_points, data), color = [PINK, VIOLET, AMBER, GREEN], markersize = 13)
    limits!(current_axis, -3.0, 0.7, -4.0, 56.0)
    limits!(error_axis, 0.5, 4.5, -160.0, 160.0)

    values = (
        lift(value -> @sprintf("Uₛ真 = %.3f V", value.true_stopping), data),
        lift(value -> @sprintf("原始阈值 = %.3f V", value.raw_estimate), data),
        lift(value -> @sprintf("外推法 = %.3f V", value.extrapolated_estimate), data),
        lift(value -> @sprintf("综合偏差 = %+.2f%%", value.corrected_error), data),
    )
    detail = lift(data) do value
        @sprintf(
            "观测截止点为 %+.3f V；先扣除暗电流和漏电斜率，再做 I^(2/3)-U 外推并修正接触电势差。",
            value.observed_cutoff,
        )
    end
    add_metrics!(metrics, values, detail)
    return figure
end

function run_self_test()
    @assert isapprox(H_OVER_E, 4.135_667_696_923_859e-15; rtol = 2.0e-15)
    @assert isapprox(HC_EV_NM, 1239.841_984_332_002_6; rtol = 2.0e-15)

    weak = iv_model(405.0, 30.0, 2.15, 80.0, 0.5)
    strong = iv_model(405.0, 90.0, 2.15, 80.0, 0.5)
    @assert isapprox(weak.stopping, strong.stopping; atol = 0.0)
    @assert strong.selected_current > weak.selected_current

    planck = planck_model(2.15, 0.12, 0.0, 5)
    @assert isapprox(planck.h_over_e_estimate, H_OVER_E; rtol = 1.0e-12)
    @assert isapprox(planck.work_estimate, 2.15; rtol = 1.0e-12)

    red_limit = HC_EV_NM / 2.15
    short_wave = threshold_model(red_limit * 0.99, 25.0, 2.15, 2.0, 1.0)
    long_wave = threshold_model(red_limit * 1.01, 100.0, 2.15, 2.0, 1.0)
    @assert short_wave.active && short_wave.current > 0
    @assert !long_wave.active && iszero(long_wave.current)
    brighter = threshold_model(405.0, 90.0, 2.15, 2.0, 1.0)
    dimmer = threshold_model(405.0, 20.0, 2.15, 2.0, 1.0)
    @assert isapprox(brighter.kinetic_energy, dimmer.kinetic_energy; atol = 0.0)
    @assert brighter.current > dimmer.current

    no_contact = uncertainty_model(405.0, 2.15, 0.0, 0.0, 0.0, 0.0)
    with_contact = uncertainty_model(405.0, 2.15, 0.12, 0.0, 0.0, 0.0)
    @assert abs((with_contact.extrapolated_estimate - no_contact.extrapolated_estimate) + 0.12) < 1.0e-6
    @assert isapprox(
        with_contact.corrected_estimate,
        no_contact.corrected_estimate;
        atol = 1.0e-6,
    )
    @assert isapprox(with_contact.corrected_estimate, with_contact.true_stopping; atol = 1.0e-6)

    for builder in (
        iv_figure,
        planck_figure,
        threshold_figure,
        uncertainty_figure,
    )
        @assert builder() isa Figure
    end
    println("光电效应四个独立网页实验自检通过。")
end

const PAGE_STYLE = """
html, body { margin: 0; width: 100%; height: 100%; background: #0b0f14; color: #eef3f8; }
body { position: relative; overflow: hidden; font-family: 'Microsoft YaHei', 'Noto Sans CJK SC', sans-serif; }
.photoelectric-lab { position: absolute; left: 0; top: 0; width: $(FIGURE_WIDTH)px; height: $(FIGURE_HEIGHT)px;
    margin: 0; padding: 0; box-sizing: border-box; overflow: hidden; background: #0b0f14;
    transform-origin: 0 0; }
.photoelectric-diagnostic {
    position: fixed; left: 16px; right: 16px; bottom: 16px; z-index: 1002;
    display: none; padding: 10px 12px; color: #f7d7d7;
    background: rgba(64, 20, 28, .94); border: 1px solid rgba(255, 85, 105, .65);
    border-radius: 6px; font: 13px/1.5 ui-monospace, Consolas, monospace;
    white-space: pre-wrap;
}
.photoelectric-diagnostic.visible { display: block; }
"""

const CLIENT_STATUS_SCRIPT = """
(() => {
    let ready = false;
    const parentWindow = window.parent || window;
    const send = (type, detail = "") => {
        parentWindow.postMessage({ type, detail }, "*");
    };
    let fitFrame = 0;
    let layoutScale = 1;
    const syncWGLPointerScale = event => {
        const canvas = event && event.target instanceof HTMLCanvasElement
            ? event.target
            : null;
        const screen = canvas && canvas.wglmakie_screen;
        if (!screen || !Number.isFinite(screen.winscale) || screen.winscale <= 0) return;
        if (!Number.isFinite(screen.__physicsBaseWinscale)) {
            screen.__physicsBaseWinscale = screen.winscale;
        }
        const baseWinscale = screen.__physicsBaseWinscale;
        screen.winscale = baseWinscale * layoutScale;
        window.clearTimeout(screen.__physicsPointerScaleTimer);
        screen.__physicsPointerScaleTimer = window.setTimeout(() => {
            if (canvas.wglmakie_screen === screen) screen.winscale = baseWinscale;
        }, 120);
    };
    const fitLayout = () => {
        const page = document.querySelector(".photoelectric-lab");
        if (!page) return;
        const viewport = window.visualViewport;
        const viewportWidth = Math.max(
            1,
            viewport ? viewport.width : (document.documentElement.clientWidth || window.innerWidth)
        );
        const viewportHeight = Math.max(
            1,
            viewport ? viewport.height : (document.documentElement.clientHeight || window.innerHeight)
        );
        const availableWidth = Math.max(1, viewportWidth - 12);
        const availableHeight = Math.max(1, viewportHeight - 8);
        const scale = Math.min(
            1.05,
            availableWidth / $(FIGURE_WIDTH),
            availableHeight / $(FIGURE_HEIGHT)
        );
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
        fitFrame = requestAnimationFrame(() => {
            fitFrame = 0;
            fitLayout();
        });
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

    for (const eventName of [
        "mousemove", "mousedown", "mouseup", "pointerdown", "pointermove",
        "pointerup", "pointercancel", "wheel"
    ]) {
        document.addEventListener(eventName, syncWGLPointerScale, {
            capture: true,
            passive: true,
        });
    }

    const showDiagnostic = detail => {
        let box = document.getElementById("photoelectric-diagnostic");
        if (!box) {
            box = document.createElement("div");
            box.id = "photoelectric-diagnostic";
            box.className = "photoelectric-diagnostic";
            document.body.appendChild(box);
        }
        box.textContent = detail;
        box.classList.add("visible");
        send("photoelectric-wgl-failed", detail);
    };
    const webglProbe = () => {
        try {
            const canvas = document.createElement("canvas");
            if (canvas.getContext("webgl2", { antialias: true })) return "webgl2";
            if (
                canvas.getContext("webgl", { antialias: true }) ||
                canvas.getContext("experimental-webgl")
            ) return "webgl1";
        } catch (error) {
            return "error: " + error.message;
        }
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
        const spinnerVisible = Boolean(
            spinner &&
            spinner.getClientRects().length > 0 &&
            getComputedStyle(spinner).visibility !== "hidden"
        );
        if (canvas && canvas.width > 0 && canvas.height > 0 && !spinnerVisible) {
            ready = true;
            send("photoelectric-wgl-ready", glStatus);
            return;
        }
        if (!ready && performance.now() - startedAt > 75000) {
            showDiagnostic(
                "WGLMakie/Bonito 初始化超过 75 秒。" +
                "\\nWebGL 状态：" + glStatus +
                "\\n页面地址：" + location.href
            );
            return;
        }
        window.setTimeout(check, 300);
    };
    window.addEventListener("error", event => {
        showDiagnostic(
            "浏览器脚本错误：" + event.message +
            "\\n" + event.filename + ":" + event.lineno
        );
    });
    window.addEventListener("unhandledrejection", event => {
        showDiagnostic("浏览器 Promise 错误：" + String(event.reason));
    });
    check();
})();
"""

function experiment_app(title, builder)
    return Bonito.App(; title = title) do
        figure = builder()
        DOM.div(
            DOM.style(PAGE_STYLE),
            DOM.div(figure; class = "photoelectric-lab"),
            DOM.script(CLIENT_STATUS_SCRIPT),
        )
    end
end

function index_app()
    links = [
        DOM.a(name; href = path, style = "color:#73d7cf;margin-right:24px")
        for (name, path) in (
            ("伏安特性与光强", "./iv"),
            ("普朗克常量拟合", "./planck"),
            ("红限与量子规律", "./threshold"),
            ("遏止电压判读与系统误差", "./uncertainty"),
        )
    ]
    return Bonito.App(
        DOM.div(
            DOM.style(PAGE_STYLE),
            DOM.h1("光电效应可视化实验"),
            DOM.div(links...),
            style = "padding:32px;background:#0b0f14;color:#eef3f8;min-height:100vh",
        );
        title = "光电效应可视化实验",
    )
end

function health_app()
    return Bonito.App(
        DOM.pre("physics-experiment:photoelectric");
        title = "physics-experiment:photoelectric",
    )
end

function main()
    load_packaged_wgl_shaders!()
    WGLMakie.activate!(; use_html_widgets = true)
    configure_theme!()
    if "--self-test" in ARGS
        run_self_test()
        return
    end
    host = get(ENV, "PHOTOELECTRIC_WEB_HOST", "127.0.0.1")
    port = parse(Int, get(ENV, "PHOTOELECTRIC_WEB_PORT", "9387"))
    proxy_url = strip(get(ENV, "PHOTOELECTRIC_WEB_PROXY_URL", "."))
    isempty(proxy_url) && (proxy_url = ".")
    server = Bonito.Server(host, port; proxy_url = proxy_url)
    Bonito.route!(server, "/__physics_health__" => health_app())
    Bonito.route!(server, "/" => index_app())
    Bonito.route!(server, "/iv" => experiment_app("伏安特性与光强", iv_figure))
    Bonito.route!(server, "/planck" => experiment_app("普朗克常量拟合", planck_figure))
    Bonito.route!(server, "/threshold" => experiment_app("红限与量子规律", threshold_figure))
    Bonito.route!(server, "/uncertainty" => experiment_app("遏止电压判读与系统误差", uncertainty_figure))
    println("光电效应网页实验已启动：http://$(host):$(port)")
    wait(server)
end

if abspath(PROGRAM_FILE) == @__FILE__
    main()
end
