# 温度传感器特性的测定：参考文献索引

## 1. 使用边界

本目录用于大学物理实验的文献检索与概念对照。六份官方免费 PDF 作为可携带全文进入专题知识库；IEC 标准和其他受限文献只保存题录、公开摘要和官方链接，不复制受限全文。课程用户应通过学校图书馆或标准机构的合法授权访问正式版。

## 2. 十篇经典/权威核心文献

### 2.1 Callendar (1887)

H. L. Callendar, “On the Practical Measurement of Temperature: Experiments Made at the Cavendish Laboratory, Cambridge,” *Philosophical Transactions of the Royal Society of London A*, 178, 161–230 (1887). DOI: [10.1098/rsta.1887.0006](https://doi.org/10.1098/rsta.1887.0006).

教学用途：铂电阻温度计的经典原始论文，理解稳定性、可重复性和铂温标的历史起点。

### 2.2 Preston-Thomas (1990)

H. Preston-Thomas, “The International Temperature Scale of 1990 (ITS-90),” *Metrologia* 27(1), 3–10 (1990). DOI: [10.1088/0026-1394/27/1/002](https://doi.org/10.1088/0026-1394/27/1/002).

教学用途：温度标定、固定点、标准铂电阻插值的官方英文文本与尺度背景。

### 2.3 IEC 60751:2022

International Electrotechnical Commission, *Industrial platinum resistance thermometers and platinum temperature sensors*, IEC 60751:2022, 3rd ed. [官方页面](https://webstore.iec.ch/en/publication/63753).

教学用途：Pt100 标称电阻—温度函数、允差类别、滞后与工业传感器性能试验的标准来源。

### 2.4 IEC 60584-1:2013

International Electrotechnical Commission, *Thermocouples — Part 1: EMF specifications and tolerances*, IEC 60584-1:2013, 3rd ed. [官方页面](https://webstore.iec.ch/en/publication/2521).

教学用途：字母型热电偶的 ITS-90 参考多项式、热电动势表、Seebeck 系数与允差。

### 2.5 Burns et al. (1993), NIST Monograph 175

G. W. Burns, M. G. Scroger, G. F. Strouse, M. C. Croarkin, and W. F. Guthrie, *Temperature-Electromotive Force Reference Functions and Tables for the Letter-Designated Thermocouple Types Based on the ITS-90*, NIST Monograph 175 (1993). DOI: [10.6028/NIST.MONO.175](https://doi.org/10.6028/NIST.MONO.175). 本地文件：`NIST_MONO_175_Thermocouples.pdf`。

教学用途：B/E/J/K/N/R/S/T 型热电偶正向/反向参考函数与表格，冷端补偿的权威数据基础。

### 2.6 Strouse (2008), NIST SP 250-81

G. F. Strouse, *Standard Platinum Resistance Thermometer Calibrations from the Ar TP to the Ag FP*, NIST Special Publication 250-81 (2008). DOI: [10.6028/NIST.SP.250-81](https://doi.org/10.6028/NIST.SP.250-81). 本地文件：`NIST_SP250_81_SPRT_Calibration.pdf`。

教学用途：固定点装置、标准铂电阻校准、电桥读数、自热修正和不确定度。

### 2.7 Strouse et al. (1998), NISTIR 6225

G. F. Strouse, B. W. Mangum, C. D. Vaughn, and E. Y. Xu, *A New NIST Automated Calibration System for Industrial-Grade Platinum Resistance Thermometers*, NISTIR 6225 (1998). DOI: [10.6028/NIST.IR.6225](https://doi.org/10.6028/NIST.IR.6225). 本地文件：`NIST_IR6225_IPRT_Automated_Calibration.pdf`。

教学用途：比较温槽、标准 Pt100、自动平衡比率电桥、恒流源和数据采集的完整校准系统。

### 2.8 BIPM CCT IPRT Guide (2021/2022)

J. Pearce et al., *Guide to Secondary Thermometry: Industrial Platinum Resistance Thermometers*, Consultative Committee for Thermometry, BIPM (2021, version 1.1 published 2022). [官方 PDF](https://www.bipm.org/documents/20126/41773843/BIPM_CCT_Guide_to_IPRTs.pdf). 本地文件：`BIPM_CCT_Guide_IPRT.pdf`。

教学用途：工业铂电阻的结构、读出、退火、稳定性、滞后、自热、校准和不确定度综合指南。

### 2.9 BIPM CCT Thermocouple Guide Part 1 (2021)

D. R. White et al., *Guide to Secondary Thermometry: Thermocouple Thermometry, Part 1 — General Usage*, Consultative Committee for Thermometry, BIPM (2021). [官方 PDF](https://www.bipm.org/documents/20126/41773843/Thermocouple_Thermometry_Part1.pdf). 本地文件：`BIPM_CCT_Thermocouple_Part1.pdf`。

教学用途：热电偶回路法则、参考端、延长/补偿导线、非均匀性、寄生结和现场安装误差。

### 2.10 JCGM 100:2008

Joint Committee for Guides in Metrology, *Evaluation of Measurement Data — Guide to the Expression of Uncertainty in Measurement*, JCGM 100:2008(E). DOI: [10.59161/JCGM100-2008E](https://doi.org/10.59161/JCGM100-2008E). 本地文件：`JCGM_100_2008_GUM.pdf`。

教学用途：A/B 类标准不确定度、灵敏系数、相关性、合成/扩展不确定度和结果报告。

## 3. 全文可携带性与校验

六份本地 PDF 均从 NIST 或 BIPM/JCGM 官方下载。`build_temperature_sensor_import.py` 会检查 `%PDF-` 签名、页数、SHA-256、文本层页数与空页，并把来源 URL 写入抽取报告。题录字段的机器可读版在上级目录 `sources.json`。
