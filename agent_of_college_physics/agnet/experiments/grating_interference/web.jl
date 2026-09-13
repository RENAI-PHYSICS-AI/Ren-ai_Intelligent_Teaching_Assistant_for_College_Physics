import Pkg; Pkg.activate(@__DIR__); "--no-instantiate" in ARGS || Pkg.instantiate()
multislit(x, n) = map(q -> abs(sin(q)) < 1e-7 ? 1.0 : (sin(n*q)/(n*sin(q)))^2, pi .* x ./ 0.01)
const LAB_SPEC = (key=:grating_interference, title="光栅干涉实验", marker="physics-experiment:grating-interference", ready_event="grating-interference-wgl-ready", failed_event="grating-interference-wgl-failed",
 reference="大学物理衍射讲义（多缝因子、缺级、R=kN）与 Newport 衍射光栅手册",
 host_env="GRATING_INTERFERENCE_WEB_HOST", port_env="GRATING_INTERFERENCE_WEB_PORT", proxy_env="GRATING_INTERFERENCE_WEB_PROXY_URL", port=9403,
 pages=Dict(
 "/principle"=>(title="多缝干涉、主极大与缺级",xmin=-0.03,xmax=0.03,xlabel="sin θ",ylabel="归一化光强",control="有效缝数",symbol="N",unit="",vmin=5.0,vmax=80.0,default=30.0,formula="I∝sinc²α·[sin(Nβ)/(N sinβ)]²；d sinθ=kλ",note="扫描观察角，比较缝数增加时主峰变窄、次极大变弱以及单缝包络导致的缺级。",model=(x,n)->multislit(x,round(Int,n))),
 "/spectrum"=>(title="分光计扫描与复色光谱",xmin=400.0,xmax=700.0,xlabel="波长 / nm",ylabel="一级衍射角 / °",control="光栅常数",symbol="d",unit="μm",vmin=1.0,vmax=4.0,default=2.0,formula="θₖ=asin(kλ/d)，左右读数取半差",note="从零级向 ±k 级扫描并成对读数；长波谱线偏转更大，注意不同级次的谱线重叠。",model=(x,d)->asind.(clamp.(x*1e-3/d,-1,1))),
 "/wavelength"=>(title="未知波长测量",xmin=1.0,xmax=4.0,xlabel="级次 k",ylabel="sin θ",control="未知波长",symbol="λ",unit="nm",vmin=450.0,vmax=680.0,default=589.3,formula="sinθ 对 k 的斜率为 λ/d",note="左右两侧取平均可削弱分光计偏心误差。",model=(x,l)->x*l/2000),
 "/resolution"=>(title="分辨本领与不确定度",xmin=100.0,xmax=3000.0,xlabel="有效刻线数 N",ylabel="分辨本领 R",control="光谱级次",symbol="k",unit="",vmin=1.0,vmax=3.0,default=1.0,formula="R = λ/Δλ = kN",note="综合角度、光栅常数和级次识别的不确定度。",model=(x,k)->k*x)))
include(joinpath(@__DIR__, "..", "parameter_lab.jl"))
