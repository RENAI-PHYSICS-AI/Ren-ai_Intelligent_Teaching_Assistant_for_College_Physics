import Pkg; Pkg.activate(@__DIR__); "--no-instantiate" in ARGS || Pkg.instantiate()
const LAB_SPEC = (key=:michelson_wavelength, title="迈克尔逊干涉仪测波长实验", marker="physics-experiment:michelson-wavelength", ready_event="michelson-wavelength-wgl-ready", failed_event="michelson-wavelength-wgl-failed",
 reference="MIT Optical Interference/Coherence 讲义与高校迈克尔逊实验手册（每 30 条纹分组、逐差与空程误差）",
 host_env="MICHELSON_WAVELENGTH_WEB_HOST", port_env="MICHELSON_WAVELENGTH_WEB_PORT", proxy_env="MICHELSON_WAVELENGTH_WEB_PROXY_URL", port=9405,
 pages=Dict(
 "/alignment"=>(title="光路调节与等倾干涉",xmin=-8.0,xmax=8.0,xlabel="屏面位置",ylabel="条纹强度",control="两镜夹角",symbol="α",unit="mrad",vmin=0.0,vmax=2.0,default=0.2,formula="M₁ 与 M₂′ 近似平行时出现同心圆环",note="先使两返回光斑重合，再微调补偿板和反射镜。",model=(x,a)->0.5 .+0.5*cos.(0.7*x.^2 .+ a*x)),
 "/counting"=>(title="移镜、条纹吞吐与累计计数",xmin=0.0,xmax=1.0,xlabel="镜面位移 / mm",ylabel="累计条纹数 N",control="微调鼓轮比例",symbol="c",unit="",vmin=0.96,vmax=1.04,default=1.0,formula="2Δd=Nλ；每 30 条纹记录一次位置",note="只沿一个方向缓慢转动鼓轮，累计 300 条以上条纹；换向前先消除空程，避免把回程差计入位移。",model=(x,c)->2e6.*x.*c./632.8),
 "/wavelength"=>(title="波长线性拟合",xmin=0.0,xmax=500.0,xlabel="条纹数 N",ylabel="镜面位移 / μm",control="波长",symbol="λ",unit="nm",vmin=500.0,vmax=650.0,default=632.8,formula="Δd 对 N 的斜率等于 λ/2",note="使用多组累计计数进行线性拟合。",model=(x,l)->x*l/2000),
 "/uncertainty"=>(title="回程差与不确定度",xmin=10.0,xmax=500.0,xlabel="累计条纹数 N",ylabel="相对计数误差",control="漏计条纹数",symbol="ΔN",unit="",vmin=0.2,vmax=3.0,default=1.0,formula="λ = 2Δd/N",note="增加累计条纹数可降低计数相对误差；位移读数须单向逼近。",model=(x,n)->n./x)))
include(joinpath(@__DIR__, "..", "parameter_lab.jl"))
