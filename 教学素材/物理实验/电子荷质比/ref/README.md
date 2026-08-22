# 电子荷质比实验经典文献与资料索引

本文件夹收集与电子荷质比（电子比荷、$e/m$）测量有关的经典原始论文、标准值资料、圆轨道法与磁聚焦法实验讲义、仪器说明，以及数字化测量和虚拟实验研究。当前目录中的 17 份 PDF 均已逐一核对，可正常读取；未保存为本地 PDF 的网页和论文入口另列于文末。

## 经典历史与标准值

1. `Thomson_1897_Cathode_Rays.pdf`
   - J. J. Thomson, “XL. Cathode Rays”, *The London, Edinburgh, and Dublin Philosophical Magazine and Journal of Science*, Series 5, 44(269), 293–316, 1897. DOI: 10.1080/14786449708621070.
   - 经典意义：Thomson 通过电场和磁场偏转研究阴极射线，论证其由具有共同荷质比的带电微粒组成，是电子发现史和荷质比测量的源头文献。其装置与现代细电子束圆轨道装置并不完全相同，适合用于实验史与原理溯源。
   - 开放存档：https://zenodo.org/records/1431235；出版物 DOI：https://doi.org/10.1080/14786449708621070

2. `NIST_2022_CODATA_Full_Report.pdf`
   - P. J. Mohr, D. B. Newell, B. N. Taylor and E. Tiesinga, “CODATA recommended values of the fundamental physical constants: 2022”, *Journal of Physical and Chemical Reference Data*, 54, 033105, 2025. DOI: 10.1063/5.0279860.
   - 用途：2022 CODATA 基本物理常数调整的完整报告，可作为实验结果比较、相对误差计算和不确定度说明的权威依据。报告给出的带符号电子荷质商为 $-e/m_e=-1.758\,820\,008\,38(55)\times10^{11}\ \mathrm{C\,kg^{-1}}$。
   - 来源：https://physics.nist.gov/cuu/pdf/JPCRD2022CODATA.pdf

3. `NIST_2022_CODATA_Fundamental_Constants.pdf`
   - National Institute of Standards and Technology, *CODATA Recommended Values of the Fundamental Physical Constants: 2022*, NIST SP 961, May 2024.
   - 用途：一页式标准值速查表，列出电子质量、元电荷和电子荷质商等常数。NIST 以电子实际电荷 $q_e=-e$ 书写，因此电子荷质商为负值；大学物理实验通常把 $e$ 定义为元电荷的正值（或直接报告绝对值），故教学中常写 $e/m_e$ 或 $|q_e|/m_e=1.758\,820\,008\,38(55)\times10^{11}\ \mathrm{C\,kg^{-1}}$。两种表述只差符号约定，并不矛盾。
   - 来源：https://physics.nist.gov/cuu/pdf/wall_2022.pdf

## 圆轨道 / 磁聚焦 / 实验讲义

4. `CCNY_Lorentz_Force_Apparatus_Instructions.pdf`
   - Sci-Supply, *Operator's Manual for Lorentz Force Apparatus: Sci-Supply Model SS20806*, undated operator's manual.
   - 用途：给出 SS20806 Bainbridge 型细电子束装置的技术参数、结构、理论、接线、操作和样例数据，可用于建立加速电压—线圈电流—轨道半径的交互关系。文件名中的 “CCNY” 表示其由 CCNY PHYS 471 实验网页链接使用；题录仍按原制造商手册著录。
   - 来源：https://hedberg.ccnysites.cuny.edu/PHYS471/experiments/chargetomass/Lorentz-Force-Apparatus-Instructions-edits.pdf

5. `Columbia_2022_Lab_Manual_Experiment4_em.pdf`
   - Columbia University Department of Physics, *Experiments in Physics: Physics 1494*, Fall 2022 Edition, Experiment 4 “e/m of the Electron”, pp. 29–36.
   - 用途：完整大学实验手册；第 4 个实验用 Helmholtz 线圈产生横向磁场，通过不同加速电压下的圆轨道半径测量、$I$ 对 $1/r$ 的线性拟合和加权平均求荷质比，并讨论环境磁场和系统误差。
   - 来源：https://www.physics.columbia.edu/sites/default/files/content/Lab%20Resources/Lab_Manual_2022_Fall.pdf

6. `Gray_2024_em_Systematic_Uncertainty.pdf`
   - N. P. Gray, T. K. Rutledge, L. Parrott, C. A. Barns and K. B. Aptowicz, “The e/m experiment: Student exploration into systematic uncertainty”, *American Journal of Physics*, 92(7), 538–544, 2024. DOI: 10.1119/5.0190546.
   - 用途：以 Bainbridge 装置为例，把传统验证性实验改造为系统不确定度探究；详细讨论磁场—电流标定、外部磁场、场不均匀、标尺错位、加速电势偏置和相对论修正，并展示如何把约 15% 的偏差降至约 0.5%。适合作为误差分析与高级实验模块依据。
   - 来源：https://www.wcupa.edu/sciences-mathematics/physics/kAptowicz/documents/2024_AJP_Gray.pdf

7. `IITK_2024_25_Physics_Lab_Manual.pdf`
   - S. Das, *PHY 111A Laboratory Manual*, Department of Physics, Indian Institute of Technology Kanpur, 2024–2025, Chapter 3 “Helmholtz Coils”, pp. 36–42.
   - 用途：该手册本身不是电子荷质比实验讲义；相关章节系统测绘 Helmholtz 线圈轴向和径向磁场并检验场的均匀性，可用于荷质比实验中的磁场标定、线圈几何和场分布可视化。
   - 来源：https://iitk.ac.in/phy/data/Manual_2024-25-I_online.pdf

8. `LD_Didactic_P6.1.3.1_Specific_Charge.pdf`
   - LD Didactic GmbH, *Determination of the Specific Charge of the Electron*, LD Physics Leaflets P6.1.3.1, undated leaflet (PDF metadata dated 2007).
   - 用途：细电子束管与 Helmholtz 线圈圆轨道法的完整实验单；固定轨道半径，测量不同加速电压下所需线圈电流，并利用 $U$ 与 $I^2$ 的线性关系求电子比荷，附带磁场标定方案。
   - 来源：https://www.ld-italia.it/uploads/4/7/2/8/47287479/p6131_e.pdf

9. `PASCO_SE-9629_em_Apparatus_Manual.pdf`
   - PASCO Scientific, *Electron Charge-to-Mass Ratio (SE-9629)*, Product Guide 012-14265F, 2023.
   - 用途：给出 PASCO SE-9629 装置的原理、安全、装配、接线和测量流程；包含横向磁场中的圆轨道、可旋转电子束管及电场偏转演示，适合映射真实仪器控件和安全约束。
   - 来源：https://cdn.pasco.com/product_document/em-Apparatus-SE-9629-Manual.pdf

10. `Rochester_Experiment08_Electron_em.pdf`
    - H. G. Yoo, *Experiment 8: Electron Beams*, University of Rochester Introductory Physics Laboratory Manual, revised 15 December 2014.
    - 用途：包含预习、装置原理、三组加速电压下的电流与束径测量、误差传播和实验记录表，可作为圆轨道法教学流程和数据表设计参考。
    - 来源：https://www.pas.rochester.edu/~physlabs/manuals/Experiment08.pdf

11. `UVA_Lab07_Electron_em.pdf`
    - University of Virginia Physics Department, *Lab 7 — Electron Charge-to-Mass Ratio*, PHYS 241W, Fall 2003.
    - 用途：从电子枪、Lorentz 力、圆周运动到 Helmholtz 线圈磁场给出细致推导和操作问题，并包含地磁影响、轨迹观察与不确定度讨论，适合分步骤教学提示设计。
    - 来源：https://galileo.phys.virginia.edu/classes/241w.gdc4k.fall03/manual/Lab07.pdf

12. `UZH_Electron_Charge_to_Mass_Ratio_Lab_Manual.pdf`
    - University of Zurich, Department of Physics, *4. Electron Charge-to-Mass Ratio*, laboratory manual, 2020.
    - 用途：同一讲义包含两套彼此独立的装置：纵向磁场中的磁聚焦法，以及横向 Helmholtz 磁场中的圆轨道偏转法。可用于比较两种测量机制、分离实验模块，并为聚焦条件和螺旋轨迹可视化提供依据。
    - 来源：https://www.physik.uzh.ch/~matthias/espace-assistant/manuals/en/anleitung_etom_e.pdf

13. `William_Mary_2014_emratio_Lab_Manual.pdf`
    - College of William & Mary, Department of Physics, *Measurement of Charge-to-Mass (e/m) Ratio for the Electron*, Experimental Atomic Physics 251 laboratory manual, 2014.
    - 用途：给出 PASCO 装置的完整推导、实验步骤、线性拟合要求、截距分析和 Helmholtz 线圈附录，适合建立数据拟合和残差分析模块。
    - 来源：https://physics.wm.edu/~evmik/classes/2014_fall_Experimental_Atomic_Physics_251/manual/emratio.pdf

## 数字化与可视化

14. `Alzate_Cardona_2019_Magnetic_Field_Visualizer.pdf`
    - J. D. Alzate-Cardona, D. Sabogal-Suárez, J. Torres and E. Restrepo-Parra, “MFV: Application software for the visualization and characterization of the DC magnetic field distribution in circular coil systems”, arXiv:1904.04327v1, 2019.
    - 用途：介绍开源 Magnetic Field Visualizer，可模拟任意共轴圆线圈系统并绘制磁场分布和均匀区；论文还以 Helmholtz 线圈实验验证计算结果，适合作为三维磁场、轴线场和均匀度热图模块依据。
    - 来源：https://arxiv.org/pdf/1904.04327

15. `Sarapak_2025_3D_Virtual_Lab_em.pdf`
    - C. Sarapak, J. Jumpatam, T. Lunnoo, N. Kongngarm, S. Raso and K. Kearns, “Comparing 3D Virtual Labs and Traditional Labs: Impact on Teacher Training and Student Learning in Physics Education”, *Jurnal Pendidikan IPA Indonesia*, 14(4), 772–783, 2025. DOI: 10.15294/jpii.v14i4.21115.
    - 用途：以电子荷质比实验为对象比较三维虚拟实验与传统实验，涉及 32 名教师和 131 名学生；可为三维装置、交互式操作、实验训练流程和学习成效设计提供教学研究依据。
    - 来源：https://journal.unnes.ac.id/journals/jpii/article/download/21115/7767/131461

16. `Silviana_Prayogi_2023_Smartphone_em.pdf`
    - F. Silviana and S. Prayogi, “Utilization of Smartphones in Experiments of Measurement of Electron-Mass Charge Ratio”, *International Journal of Engineering and Science Applications*, 10(1), 22–27, 2023. DOI: 10.20956/ijesca.v10i1.4893.
    - 用途：用智能手机磁力计与 Kelmscott Gauss Meter 应用测 Helmholtz 磁场，并用手机相机和 Tracker 图像处理测圆轨道半径；适合作为传感器校准、图像拾取、圆拟合和数字化采集模块参考。
    - 来源：https://pasca.unhas.ac.id/ojs/index.php/ijesca/article/view/4893/899

## 中文资料

17. `TJNU_电子比荷的测定_DH4520.pdf`
    - 天津师范大学，《电子比荷的测定》，DH4520 型电子比荷测定仪实验资料，未署作者和日期。
    - 用途：中文讲义涵盖电场偏转、Lorentz 力、Helmholtz 线圈、圆轨道与螺旋轨迹观察，以及加速电压、线圈电流和轨道直径的测量；适合作为中文操作说明、术语和界面提示的直接依据。
    - 来源：https://www.tjnu.edu.cn/__local/0/DF/B5/6ED4C36D8DF9F5EA65EB1DC86D6_96CA7AE8_56E08.pdf

## 在线但未本地保存

以下条目仅登记在线入口；当前 `ref` 目录中没有对应的本地 PDF。它们不计入上面的 17 份本地资料。

- K. T. Bainbridge, “The Specific Charge of the Electron”, *The American Physics Teacher*, 6(1), 35–36, 1938. DOI: 10.1119/1.1991259.
  - 用途：Bainbridge 面向教学实验改进了可见电子束测量装置，是理解现代细束管—亥姆霍兹线圈实验与 Thomson 原始阴极射线实验之间演变的重要文献。
  - 在线入口：https://doi.org/10.1119/1.1991259

- 王玉清、杨能勋、薛琳娜，《磁聚焦法测量电子荷质比实验中励磁电流测量方法的研究》，《大学物理》，2012，31(3)，44–46。
  - 用途：讨论磁聚焦法中励磁电流测量及其误差，适合补充聚焦法测量链和误差来源。
  - 在线入口：https://dxwl.bnu.edu.cn/CN/Y2012/V31/I3/44

- UCLA Physics & Astronomy, “Experiment 6 — The Charge-to-Mass Ratio of the Electron”.
  - 用途：Kent TG-13 装置的在线实验说明，包含圆周运动与螺旋运动观察、理论公式和操作步骤，可补充不同磁场入射角下的轨迹可视化。
  - 在线入口：https://demoweb.physics.ucla.edu/content/experiment-6-charge-mass-ratio-electron

- University of Tasmania Physics, POLUS, “Charge-to-mass ratio of the electron”.
  - 用途：介绍 Hoag 纵向磁聚焦法，利用电子束重新聚焦条件测量荷质比，适合作为磁聚焦独立模块的在线参考。
  - 在线入口：https://polus.utasphys.cloud.edu.au/syl/kya212/eonm/

- Kansas State University Physics Laboratory, “The Hoag e/m Apparatus”.
  - 用途：转载 Welch Hoag 装置资料，介绍纵向磁聚焦操作、螺旋轨迹与聚焦条件，可与 UZH 讲义交叉核对磁聚焦页面。
  - 在线入口：https://www.phys.ksu.edu/personal/cocke/classes/phys506/emhoag.htm

- Indian Institute of Technology Roorkee, “e/m Experiment (Magnetron Method)”.
  - 用途：给出磁控管截止法的装置、Hull 截止近似、阳极电流—磁场曲线和 $V_a-B_c^2$ 数据处理，作为第二阶段磁控管页面依据。
  - 在线入口：https://www.iitr.ac.in/Academics/static/Department/Physics/PH-202/12._ebym_magnetron_method.pdf

- James Hedberg, The City College of New York, PHYS 471, “Exp 3: Charge to Mass (or E/M)”.
  - 用途：实验网页把 SS20806 手册、图像采集、线剖面分析、代码和数据处理组织在同一教学流程中；其链接的 Sci-Supply 手册已作为第 4 条保存，本网页本身未保存为 PDF。
  - 在线入口：https://hedberg.ccnysites.cuny.edu/PHYS471/experiments/chargetomass/

- F. A. J. Duque, S. V. Duarte and F. J. R. Niebles, “Computational Thinking Through a Dynamic Simulation of the Electron Charge-Mass Ratio”, *IEEE Revista Iberoamericana de Tecnologías del Aprendizaje*, 2025. DOI: 10.1109/RITA.2025.3593422.
  - 用途：以动态仿真和计算思维组织电子荷质比教学，可用于参数联动、轨迹预测和探究任务设计。
  - 在线入口：https://doi.org/10.1109/RITA.2025.3593422

- A. Gelir, M. Kocaman and I. Pekacar, “Image processing for quantitative measurement of e/m in the undergraduate laboratory”, *Physics Education*, 54(5), 055012, 2019. DOI: 10.1088/1361-6552/ab299f.
  - 用途：用图像处理自动提取电子束圆轨道几何量，适合圆检测、标尺校准和重复测量可视化。
  - 在线入口：https://doi.org/10.1088/1361-6552/ab299f

- M. Pirbhai, “Smartphones and Tracker in the e/m experiment”, *Physics Education*, 55(1), 015001, 2020. DOI: 10.1088/1361-6552/ab49d3.
  - 用途：以手机视频和 Tracker 软件处理电子束轨迹，适合低成本图像采集和拟合流程参考。
  - 在线入口：https://doi.org/10.1088/1361-6552/ab49d3

- Universitat de València, “Electron charge-to-mass ratio” virtual laboratory.
  - 用途：提供浏览器中的电子荷质比交互实验案例，可用于比较参数组织、操作顺序和结果反馈方式；其界面不是本项目的实现要求。
  - 在线入口：https://www.uv.es/inecfis/QPhVL/p3/p3_pres.html

- Open Source Physics / Easy Java Simulations, “e/m with Helmholtz Coils”.
  - 用途：展示亥姆霍兹线圈与电子轨迹的教学仿真，可作为轨迹、磁场和参数联动的交互参考。
  - 在线入口：https://academics.eckerd.edu/physics/EJS/Intro/magnetism/Field%20and%20Currents/ejs_ntnu_em_HelmholtzCoils.html
