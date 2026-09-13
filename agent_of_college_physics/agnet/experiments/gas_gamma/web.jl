import Pkg; Pkg.activate(@__DIR__); "--no-instantiate" in ARGS || Pkg.instantiate()
const LAB_SPEC = (key=:gas_gamma, title="气体 γ 常数测定实验", marker="physics-experiment:gas-gamma", ready_event="gas-gamma-wgl-ready", failed_event="gas-gamma-wgl-failed",
 reference="UZH Clément–Desormes 实验讲义（状态 1→2→3、液柱外推）与 Gdańsk 热容比实验讲义",
 host_env="GAS_GAMMA_WEB_HOST", port_env="GAS_GAMMA_WEB_PORT", proxy_env="GAS_GAMMA_WEB_PROXY_URL", port=9402,
 pages=Dict(
 "/process"=>(title="绝热膨胀与等容升温", xmin=0.0,xmax=8.0,xlabel="时间 / s",ylabel="绝对压强 / kPa",control="初始压强差",symbol="Δp₁",unit="kPa",vmin=1.0,vmax=8.0,default=4.0,formula="状态 1→2 近似绝热；状态 2→3 等容回温",note="先缓慢加压至热平衡；快速开启并立即关闭阀门，再等容回温读取终态压差。",model=(x,p)->101.3 .+ ifelse.(x .< 2.0,p,ifelse.(x .< 2.35,0.06p,0.06p .+ 0.34p.*(1 .- exp.(-(x.-2.35)./1.55))))),
 "/pressure"=>(title="压强差读数与液柱外推", xmin=0.0,xmax=60.0,xlabel="阀门关闭后时间 / s",ylabel="液柱压差 / kPa",control="终态压强差",symbol="Δp₃",unit="kPa",vmin=0.2,vmax=3.8,default=1.15,formula="ln(h∞−hₜ) 对 t 线性拟合并外推瞬时读数",note="按 10、20…60 s 读取液柱；避免把阻尼振荡中的瞬时值直接当作终态值。",model=(x,p)->p .- 0.55p.*exp.(-x./18) .+ 0.18p.*exp.(-x./8).*sin.(2pi.*x./7)),
 "/gamma"=>(title="γ 值计算与气体比较", xmin=0.0,xmax=5.0,xlabel="Δp₂ / kPa",ylabel="γ",control="初始压强差",symbol="Δp₁",unit="kPa",vmin=2.0,vmax=8.0,default=4.0,formula="空气理论值约 1.40",note="分母较小时读数误差会被显著放大。",model=(x,p)->p./max.(p.-x,0.25)),
 "/uncertainty"=>(title="重复测量与不确定度", xmin=1.0,xmax=10.0,xlabel="测量次数",ylabel="均值标准不确定度",control="单次标准差",symbol="s",unit="",vmin=0.005,vmax=0.08,default=0.03,formula="u_A = s / √n",note="检查漏气、放气时间与回温不足造成的系统偏差。",model=(x,p)->p./sqrt.(x))))
include(joinpath(@__DIR__, "..", "parameter_lab.jl"))
