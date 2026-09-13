import Pkg; Pkg.activate(@__DIR__); "--no-instantiate" in ARGS || Pkg.instantiate()
const LAB_SPEC = (key=:light_polarization, title="光的偏振研究实验", marker="physics-experiment:light-polarization", ready_event="light-polarization-wgl-ready", failed_event="light-polarization-wgl-failed",
 reference="高校偏振实验讲义（马吕斯定律、波片、布儒斯特角）与 Damian、Monteiro 偏振测量论文",
 host_env="LIGHT_POLARIZATION_WEB_HOST", port_env="LIGHT_POLARIZATION_WEB_PORT", proxy_env="LIGHT_POLARIZATION_WEB_PROXY_URL", port=9404,
 pages=Dict(
 "/malus"=>(title="马吕斯定律",xmin=0.0,xmax=360.0,xlabel="检偏器角度 / °",ylabel="相对光强",control="偏振度",symbol="P",unit="",vmin=0.1,vmax=1.0,default=1.0,formula="I = I₀ cos²θ",note="转动检偏器并记录一周光强，观察 180° 周期。",model=(x,p)->(1-p)./2 .+ p*cosd.(x).^2),
 "/brewster"=>(title="布儒斯特角",xmin=0.0,xmax=85.0,xlabel="入射角 / °",ylabel="p 光反射率",control="折射率",symbol="n",unit="",vmin=1.3,vmax=1.8,default=1.52,formula="tan i_B = n₂/n₁",note="在布儒斯特角附近 p 偏振反射分量趋近于零。",model=(x,n)->abs2.((n*cosd.(x).-sqrt.(max.(0,n^2 .- sind.(x).^2)))./(n*cosd.(x).+sqrt.(max.(0,n^2 .- sind.(x).^2))))),
 "/waveplate"=>(title="波片、相位延迟与偏振椭圆",xmin=0.0,xmax=360.0,xlabel="检偏器角度 / °",ylabel="相对光强",control="波片相位延迟",symbol="δ",unit="°",vmin=0.0,vmax=180.0,default=90.0,formula="I/I₀ = [1 + cosδ sin(2θ)]/2",note="45° 线偏振通过四分之一波片后，检偏光强不随角度变化；改变相延迟可观察椭圆偏振到线偏振的转换。",model=(x,d)->0.5.*(1 .+ cosd(d).*sind.(2 .* x))),
 "/fit"=>(title="偏振度拟合、残差与误差",xmin=0.0,xmax=360.0,xlabel="检偏器角度 / °",ylabel="探测器电压 / V",control="暗电压偏置",symbol="U₀",unit="V",vmin=0.0,vmax=0.2,default=0.04,formula="I=U₀+C+A cos2θ+B sin2θ；P=hypot(A,B)/C",note="先遮光校零，再按 5° 或 10° 自动采集；拟合角度零点、有限消光、背景光并检查残差。",model=(x,u)->u .+ cosd.(x .- 3).^2)))
include(joinpath(@__DIR__, "..", "parameter_lab.jl"))
