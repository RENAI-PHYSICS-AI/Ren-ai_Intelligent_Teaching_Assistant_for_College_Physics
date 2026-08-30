# 三棱镜折射率测定：参考文献索引

## 1. 使用与溯源边界

本目录供大学物理实验教学、数据复核和专题检索使用。六份本地 PDF 均来自原发布机构的公开地址：SCHOTT 两份技术资料、三所大学的实验讲义及 JCGM/BIPM 的 GUM。ISO 标准、经典教材和历史文献仅保存题录与公开入口，不复制受限全文。`sources.json` 保存机器可读题录；知识库构建器记录 PDF 的原始 URL、SHA-256、页数、文本层与抽取页码。

## 2. 十篇经典/权威核心文献

### 2.1 Newton (1704)

Isaac Newton, *Opticks: or, A Treatise of the Reflexions, Refractions, Inflexions and Colours of Light* (1704). [剑桥大学数字图书馆原书扫描](https://cudl.lib.cam.ac.uk/view/PR-ADV-B-00039-00026/1)。

教学用途：用棱镜实验建立白光色散的历史起点；理解颜色并非由棱镜“染成”，而与不同波长的折射差异有关。

### 2.2 Cauchy (1836)

Augustin-Louis Cauchy, “Mémoire sur la dispersion de la lumière,” *Nouveaux exercices de mathématiques* (1836). [法国国家图书馆目录](https://catalogue.bnf.fr/ark:/12148/cb30208200v)。

教学用途：可见区远离吸收带时，折射率常可用 $n=a+b/\lambda^2+c/\lambda^4+\cdots$ 表示；本实验用两参数式作教学拟合。

### 2.3 ISO 21395-1:2020

International Organization for Standardization, *Optics and photonics — Test method for refractive index of optical glasses — Part 1: Minimum deviation method*, ISO 21395-1:2020. [ISO 官方页面](https://www.iso.org/standard/70857.html)。

教学用途：最小偏向法的标准化计量背景。正式标准文本须通过学校或机构授权获取。

### 2.4 Jenkins & White (1976)

F. A. Jenkins and H. E. White, *Fundamentals of Optics*, 4th ed., McGraw-Hill (1976). [WorldCat 题录](https://search.worldcat.org/title/1996393)。

教学用途：几何光学、棱镜偏向、最小偏向条件、分光计和色散的经典教材推导。

### 2.5 SCHOTT TIE-29 (2023)

SCHOTT Advanced Optics, *TIE-29: Refractive Index and Dispersion*, version August 2023. [官方 PDF](https://media.schott.com/api/public/content/aaa572afd854434fb7b3faa4bc46103f?download=true&v=06988a0a)。本地文件：`SCHOTT_TIE29_Refractive_Index_Dispersion.pdf`。

教学用途：Snell 定律、标准谱线、主色散、Abbe 数、Sellmeier 方程、折射率温度依赖及工业最小偏向测量。

### 2.6 SCHOTT Optical Glass Pocket Catalog (2025)

SCHOTT Advanced Optics, *Optical Glass Pocket Catalog* (2025). [官方 PDF](https://media.schott.com/api/public/content/b37dbd8fa7e64662b2d0ae523ae56238?download=true&v=97f67105)。本地文件：`SCHOTT_Optical_Glass_Pocket_Catalog.pdf`。

教学用途：按 Fraunhofer/Hg/He 标准谱线查光学玻璃的 $n_d,n_F,n_C$、Abbe 数和 Sellmeier 系数，用于校验实验数量级。

### 2.7 UC Irvine Advanced Lab

University of California, Irvine, *Faraday Rotation: Prism Angle and Refractive Index Measurements*. [大学官方 PDF](https://www.physics.uci.edu/~advanlab/faraday.pdf)。本地文件：`UCI_Faraday_Prism_Refractometry.pdf`。

教学用途：Gaussian 目镜、无穷远调焦、自准直测顶角、最小偏向的两种测量路径及双向复核。

### 2.8 College of San Mateo Physics 270

College of San Mateo Physics Department, *Physics 270 Lab 6: Prism Spectrometer*. [大学官方 PDF](https://collegeofsanmateo.edu/physics/docs/physics270/lab06.pdf)。本地文件：`CSM_Prism_Spectrometer_Lab06.pdf`。

教学用途：同一游标读数、跨零处理、反射像测顶角、逐条 He 谱线寻找转向点，以及 $n$ 对 $\lambda^{-2}$ 的最小二乘拟合。

### 2.9 University of Rochester Student Spectrometer

University of Rochester Department of Physics and Astronomy, *Experiment 14: Student Spectrometer* (2021). [大学官方 PDF](https://www.pas.rochester.edu/~physlabs/manuals/Experiment14.pdf)。本地文件：`Rochester_Student_Spectrometer_Experiment14.pdf`。

教学用途：目镜、望远镜和准直管的调节顺序；棱镜与光栅的差别；最小偏向位置的“谱线转向”判据。

### 2.10 JCGM 100:2008

Joint Committee for Guides in Metrology, *Evaluation of Measurement Data — Guide to the Expression of Uncertainty in Measurement*, JCGM 100:2008(E). DOI: [10.59161/JCGM100-2008E](https://doi.org/10.59161/JCGM100-2008E)。本地文件：`JCGM_100_2008_GUM.pdf`。

教学用途：从 $A$、$\delta_{\min}$ 和重复读数建立测量模型，计算灵敏系数、合成标准不确定度与扩展不确定度。

## 3. 本地 PDF 清单与验证

| 文件 | 发布方 | 核心用途 |
|---|---|---|
| `SCHOTT_TIE29_Refractive_Index_Dispersion.pdf` | SCHOTT | 折射率、色散、Abbe 数和测量方法 |
| `SCHOTT_Optical_Glass_Pocket_Catalog.pdf` | SCHOTT | 标准谱线与玻璃数据 |
| `UCI_Faraday_Prism_Refractometry.pdf` | UC Irvine | 顶角、最小偏向、双向复核 |
| `CSM_Prism_Spectrometer_Lab06.pdf` | College of San Mateo | 分光计实验程序与 Cauchy 拟合 |
| `Rochester_Student_Spectrometer_Experiment14.pdf` | University of Rochester | 调焦、游标与最小偏向操作 |
| `JCGM_100_2008_GUM.pdf` | JCGM/BIPM | 不确定度评定 |

构建时要求每份文件以 `%PDF-` 开头、页数大于零且存在可用文本层；校验值写入 `prism_refractive_index.extraction_report.json`，不在此处硬编码会随官方修订变化的哈希。
