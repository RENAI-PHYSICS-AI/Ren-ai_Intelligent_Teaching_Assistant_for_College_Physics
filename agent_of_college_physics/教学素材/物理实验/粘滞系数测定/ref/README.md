# 粘滞系数测定参考文献与本地资料

本目录服务于“落球法测定液体动力黏度”教学与知识库检索。题录优先指向原始论文、出版社页面或机构仓储；只在许可明确或公开可获时保存全文。本地 PDF 用于检索与备课，引用时仍应以下列原始题录为准。

## 1. 教学主线

- 牛顿黏性液体的动力黏度记为 $\eta$，单位为 Pa·s；运动黏度为 $\nu=\eta/\rho_f$，单位为 m²/s，两者不可混用。
- 球在无限介质、低雷诺数且无滑移边界下的 Stokes 阻力为 $F_d=6\pi\eta rv$。
- 达到终端速度 $v_t$ 后，重力、浮力和黏滞阻力平衡，有

$$
v_t=\frac{2r^2g(\rho_s-\rho_f)}{9\eta},
\qquad
\eta=\frac{(\rho_s-\rho_f)gd^2t}{18L}.
$$

- 实验还必须检查 $\mathrm{Re}=\rho_f v_t d/\eta$、球是否达到终速、球管直径比 $\lambda=d/D$、端部距离、温度稳定性与球的球形度。
- 对圆管轴线上的蠕动流教学修正，本项目统一定义

$$
f(\lambda)=1-2.10444\lambda+2.08877\lambda^3-0.94813\lambda^5,
\qquad
v_{\rm tube}=f(\lambda)v_\infty.
$$

因 $0<f<1$，若先用管内实测速度得到 $\eta_{\rm app}$，则壁面修正方向为 $\eta=f\eta_{\rm app}$。有些文献把阻力比 $K=1/f>1$ 称为修正因子，引用时必须说明定义，不能把乘除方向写反。

## 2. 核心经典文献（10 篇/部）

### 2.1 Stokes 1845：流体内摩擦的理论起点

G. G. Stokes, “On the Theories of the Internal Friction of Fluids in Motion, and of the Equilibrium and Motion of Elastic Solids,” *Transactions of the Cambridge Philosophical Society*, **8**, 287–319 (1845; volume issued 1849).

- 用途：牛顿型内摩擦、黏性应力和低速流动理论背景。
- 题录/公开扫描：[Cambridge Digital Library 搜索入口](https://cudl.lib.cam.ac.uk/)；[公开 PDF 镜像](https://pages.mtu.edu/~fmorriso/cm310/StokesLaw1845.pdf)。
- 本地：`Stokes_1845_Internal_Friction.pdf`，为公共领域《Mathematical and Physical Papers》第 1 卷扫描；知识库只索引该文对应的物理 PDF 第 91–145 页（书内页码 75–129）。

### 2.2 Stokes 1851：球在黏性流体中的阻力

G. G. Stokes, “On the Effect of the Internal Friction of Fluids on the Motion of Pendulums,” *Transactions of the Cambridge Philosophical Society*, **9**, 8–106 (1851).

- 用途：Stokes 阻力、蠕动流极限和落球法的理论基础。
- 原始资料：[Wellcome Collection 公共领域扫描与题录](https://wellcomecollection.org/works/hcy5wuu4)。
- 本地：`Stokes_1851_Pendulums_Internal_Friction.pdf`，使用同一公共领域扫描的 Internet Archive 文字层版本，便于知识库检索。

### 2.3 Reynolds 1883：雷诺数与流动相似

O. Reynolds, “An Experimental Investigation of the Circumstances Which Determine Whether the Motion of Water Shall Be Direct or Sinuous, and of the Law of Resistance in Parallel Channels,” *Philosophical Transactions of the Royal Society of London*, **174**, 935–982 (1883).

- 用途：理解惯性力/黏性力比和为什么落球公式要求 $\mathrm{Re}\ll1$。
- 原始文献：[Royal Society DOI](https://doi.org/10.1098/rstl.1883.0029)。

### 2.4 Basset 1888：非定常球运动与历史力

A. B. Basset, “On the Motion of a Sphere in a Viscous Liquid,” *Philosophical Transactions of the Royal Society A*, **179**, 43–63 (1888).

- 用途：说明释放初期不只有准定常 Stokes 阻力；附加质量和历史项使单指数过渡只是教学近似。
- 原始文献：[Royal Society DOI](https://doi.org/10.1098/rsta.1888.0003)。

### 2.5 Ladenburg 1907：容器壁面对落球的影响

R. Ladenburg, “Über den Einfluß von Wänden auf die Bewegung einer Kugel in einer reibenden Flüssigkeit,” *Annalen der Physik*, **328**(8), 447–458 (1907).

- 用途：有限容器中阻力增大、一阶壁面修正和球管尺度比的实验意义。
- 出版社页面：[Wiley DOI](https://doi.org/10.1002/andp.19073280806)。

### 2.6 Faxén 1923：圆柱管轴线上球的壁面修正

H. Faxén, “Die Bewegung einer starren Kugel längs der Achse eines mit zäher Flüssigkeit gefüllten Rohres,” *Arkiv för Matematik, Astronomi och Fysik*, **17**, 1–28 (1923).

- 用途：圆管轴线落球的高阶壁面修正；项目中的五次多项式使用 $\lambda=d/D=r/R$。
- 题录：[CiNii Research 学术记录](https://cir.nii.ac.jp/crid/1570291226056169472)；[原刊卷扫描](https://play.google.com/store/books/details?id=qT1KAAAAMAAJ)。
- 注意：Faxén 1922 年 *Annalen der Physik* 论文的题名是两平行平面壁问题，不宜单独当作圆管多项式的原始题录。

### 2.7 Bacon 1936：落球黏度测量与修正的系统整理

L. R. Bacon, “Measurement of Absolute Viscosity by the Falling Sphere Method,” *Journal of the Franklin Institute*, **221**(2), 251–273 (1936).

- 用途：装置设计、标定、壁面/端部效应和落球黏度计的历史性综述。
- 出版社题录：[Elsevier DOI](https://doi.org/10.1016/S0016-0032(36)90395-2)。

### 2.8 Haberman and Sayre 1958：圆管内刚性球与流体球

W. L. Haberman and R. M. Sayre, *Motion of Rigid and Fluid Spheres in Stationary and Moving Liquids Inside Cylindrical Tubes*, David Taylor Model Basin Report 1143 (1958).

- 用途：不同 $d/D$ 下的球阻力、壁面效应与理论/实验对照。
- 机构题录：[MIT DOME 稳定记录](https://dome.mit.edu/handle/1721.3/48988)；[DTIC 公开备份](https://archive.org/details/DTIC_AD0206307)；[DOI](https://doi.org/10.21236/AD0206307)。
- 本地：`Haberman_Sayre_1958_Cylindrical_Tubes.pdf`（公开 DTIC 扫描）。

### 2.9 Tanner 1963：落球黏度计的端部效应

R. I. Tanner, “End Effects in Falling-Ball Viscometry,” *Journal of Fluid Mechanics*, **17**(2), 161–170 (1963).

- 用途：球接近封闭端时的附加阻力和有效计时区设计。
- 出版社页面：[Cambridge Core DOI](https://doi.org/10.1017/S002211206300121X)。
- 适用边界：论文的数量结论针对轴向落球、Stokes 流近似与其研究几何；不能概括成任意实验只要距端部一个管半径就“绝对无端部效应”。

### 2.10 Happel and Brenner 1965：低雷诺数流体力学系统著作

J. Happel and H. Brenner, *Low Reynolds Number Hydrodynamics: With Special Applications to Particulate Media*, Prentice-Hall (1965); later reprint, Martinus Nijhoff (1983).

- 用途：蠕动流方程、球阻力、流体中颗粒运动和边界修正的系统参考。
- 出版社页面：[Springer DOI](https://doi.org/10.1007/978-94-009-8352-6)。

## 3. 高精度与计量补充资料

1. A. Brizard, M. Megharfi, E. Mahe and C. Verdier, “Design of a High Precision Falling-Ball Viscometer,” *Review of Scientific Instruments*, **76**, 025109 (2005), [DOI](https://doi.org/10.1063/1.1851471), [HAL 作者稿](https://hal.science/hal-00197586). 本地：`Brizard_et_al_2005_High_Precision_Falling_Ball.pdf`。
2. JCGM 100:2008, *Evaluation of Measurement Data—Guide to the Expression of Uncertainty in Measurement*, [DOI](https://doi.org/10.59161/JCGM100-2008E). 本地：`JCGM_100_2008_GUM.pdf`。
3. B. N. Taylor and C. E. Kuyatt, *Guidelines for Evaluating and Expressing the Uncertainty of NIST Measurement Results*, NIST Technical Note 1297 (1994), [DOI](https://doi.org/10.6028/NIST.TN.1297). 本地：`NIST_TN1297_Uncertainty.pdf`。
4. N. S. Cheng, “Formula for the Viscosity of a Glycerol-Water Mixture,” *Industrial & Engineering Chemistry Research*, **47**, 3285–3288 (2008), [DOI](https://doi.org/10.1021/ie071349z). 用于说明温度和浓度对参考黏度的显著影响。
5. 庞玮、陈小云、黄时中：“基于 Tracker 的落球法测定液体黏度实验”，*大学物理* **31**(4), 25–29 (2012), [期刊页面](https://dxwl.bnu.edu.cn/CN/Y2012/V31/I4/25)。用于视频轨迹和终速区判别的教学补充。

## 4. 本地 PDF 与授权边界

| 文件 | 来源 | 索引范围 | 备注 |
|---|---|---|---|
| `Stokes_1845_Internal_Friction.pdf` | Internet Archive 公共领域论文集 | 物理 PDF 第 91–145 页 | 对应书内页码 75–129，引用以原题录为准 |
| `Stokes_1851_Pendulums_Internal_Friction.pdf` | Wellcome Collection / Internet Archive | 全文 | Public Domain Mark；本地使用带 OCR 文字层版 |
| `Haberman_Sayre_1958_Cylindrical_Tubes.pdf` | DTIC/机构仓储 | 全文 | 圆管壁面效应核心资料 |
| `Brizard_et_al_2005_High_Precision_Falling_Ball.pdf` | HAL 作者稿 | 全文 | 题录连接与出版版 DOI 均保留 |
| `JCGM_100_2008_GUM.pdf` | BIPM/JCGM | 第 17–40 页 | 不确定度的基本定义与传播 |
| `NIST_TN1297_Uncertainty.pdf` | NIST | 第 4–16 页 | 结果表达与扩展不确定度 |

其余受访问或版权限制的经典文献只保留 DOI 与摘要性导读，不在项目中转存全文。

## 5. 实验与检索使用边界

- “粘滞系数”、“黏滞系数”、“粘度”和“黏度”在检索中均可命中本专题；物理量的规范名称在正文中优先写“动力黏度”。
- 本专题针对牛顿液体、刚性光滑球、近轴线下落和低雷诺数。非牛顿液体、球偏心、气泡、液滴、显著惯性或滑移边界不能直接套用。
- 落球过程中禁止手指伸入高粘、高温、腐蚀性或有毒液体；清洗液与废液按实验室安全规程处理。
- 可视化页面中的“真值”、扰动和参考数据是教学模型，不替代温度计、标准黏度液或计量校准。
