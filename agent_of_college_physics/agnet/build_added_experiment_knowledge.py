from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

from build_viscosity_import import atomic_write_text, clean, extract_pdf, make_row, relative_path, split_chunks, write_json
from config import IMPORTED_KB_DIR, PROJECT_ROOT


SPECS = {
    "gas_gamma": {
        "folder": "气体gamma常数测定", "topic": "气体γ常数测定", "chapter": "第5章 热力学基础",
        "routes": ["process", "pressure", "gamma", "uncertainty"],
        "method": "Clément-Desormes 快速绝热膨胀与等容回温法",
        "quantity": "热容比 γ=Cp/Cv、两次稳态压强差与合成不确定度",
        "pdfs": {"UZH_Clement_Desormes.pdf": ("Ratio of Specific Heats", 2017), "Gdansk_Specific_Heat_Ratio.pdf": ("Determination of the Ratio of Specific Heats of Air", 2021)},
        "refs": [
            ("Clément; Desormes",1819,"Mémoire sur la chaleur spécifique des gaz","Annales de Chimie et de Physique","经典原始工作","https://gallica.bnf.fr/"),
            ("J. C. Carpenter",1935,"Determination of the Ratio of Specific Heats of a Gas by Method of Clement and Desormes","Field and Laboratory","经典实验方法","https://scholar.smu.edu/fieldandlab/vol3/iss2/6/"),
            ("University of Zurich",2017,"Ratio of Specific Heats","UZH Physics","实验装置与状态过程","https://www.physik.uzh.ch/~matthias/espace-assistant/manuals/en/anleitung-cd_e.pdf"),
            ("Gdańsk University of Technology",2021,"Determination of the Ratio of the Specific Heats of Air","GUT","公式推导与测量步骤","https://pg.edu.pl/files/ftims/2021-03/SKRYPT08.pdf"),
            ("Tallinn University of Technology",2021,"Specific Heat Capacity Ratio for Gases","TalTech","液柱读数与实验问题","https://haldus.taltech.ee/sites/default/files/2021-04/Experiment_19.pdf"),
            ("University of Jordan",2025,"Thermodynamics Lab Manual: Ratio of Specific Heats of Air","University of Jordan","工程热力学实验","https://engineering.ju.edu.jo/Laboratories/Thermodynamics%20Lab%20Manual.pdf"),
            ("Jeremy Tatum",2020,"The Clément-Desormes Experiment","Physics LibreTexts","热力学状态推导","https://phys.libretexts.org/Bookshelves/Thermodynamics_and_Statistical_Mechanics/Heat_and_Thermodynamics_(Tatum)/08%3A_Heat_Capacity_and_the_Expansion_of_Gases/8.05%3A_The_Clement-Desormes_Experiment"),
            ("H. Rüchardt",1929,"Eine einfache Methode zur Bestimmung von Cp/Cv","Physikalische Zeitschrift","替代振动法","https://ui.adsabs.harvard.edu/abs/1929PhyZ...30...58R"),
            ("JCGM",2008,"Evaluation of Measurement Data - Guide to the Expression of Uncertainty in Measurement","BIPM","不确定度评定","https://doi.org/10.59161/JCGM100-2008E"),
            ("NIST",2023,"NIST Chemistry WebBook: Thermophysical Properties of Fluid Systems","NIST","气体热容参考数据","https://webbook.nist.gov/chemistry/fluid/"),
        ],
    },
    "grating_interference": {
        "folder": "光栅干涉", "topic": "光栅干涉", "chapter": "第11章 波动光学",
        "routes": ["principle", "spectrum", "wavelength", "resolution"], "method": "夫琅禾费多缝干涉、光栅方程与分光计测角", "quantity": "光栅常数 d、谱线波长 λ、角色散与分辨本领 R",
        "pdfs": {"MIT_Holographic_Imaging_Grating.pdf": ("Holographic Imaging Lab Notes: Diffraction Gratings", 2003)},
        "refs": [
            ("Joseph von Fraunhofer",1821,"Neue Modifikation des Lichtes durch gegenseitige Einwirkung und Beugung der Strahlen","Denkschriften der Bayerischen Akademie","夫琅禾费衍射经典工作","https://www.deutsche-digitale-bibliothek.de/"),
            ("H. A. Rowland",1882,"On Concave Gratings for Optical Purposes","Philosophical Magazine","凹面光栅经典论文","https://doi.org/10.1080/14786448208627217"),
            ("A. H. Holographic Imaging Staff",2003,"Holographic Imaging Lab Notes: Diffraction Gratings","MIT OpenCourseWare","光栅方程与全息光栅","https://ocw.mit.edu/courses/mas-450-holographic-imaging-spring-2003/resources/lab3/"),
            ("MIT EECS",2005,"Modern Optics Project Laboratory: Fraunhofer Diffraction","MIT OpenCourseWare","多缝和孔径衍射","https://ocw.mit.edu/courses/6-161-modern-optics-project-laboratory-fall-2005/resources/lab3/"),
            ("E. G. Loewen; E. Popov",1997,"Diffraction Gratings and Applications","Marcel Dekker","光栅理论专著","https://doi.org/10.1201/9780203752560"),
            ("Christopher Palmer",2020,"Diffraction Grating Handbook","MKS/Newport","工程光栅权威手册","https://www.newport.com/n/the-grating-equation"),
            ("NIST",2022,"Atomic Spectra Database","NIST","标准谱线波长","https://physics.nist.gov/asd"),
            ("J. W. Goodman",2005,"Introduction to Fourier Optics","Roberts","傅里叶光学理论","https://books.google.com/books?id=ow5xs_Rtt9AC"),
            ("JCGM",2008,"Guide to the Expression of Uncertainty in Measurement","BIPM","测角与波长不确定度","https://doi.org/10.59161/JCGM100-2008E"),
            ("ISO",2017,"ISO 10110-8 Optics and photonics - Preparation drawings - Surface texture","ISO","光学元件与光栅规范背景","https://www.iso.org/standard/67583.html"),
        ],
    },
    "light_polarization": {
        "folder": "光的偏振研究", "topic": "光的偏振研究", "chapter": "第11章 波动光学",
        "routes": ["malus", "brewster", "waveplate", "fit"], "method": "起偏-检偏、马吕斯定律、布儒斯特角与波片相位延迟", "quantity": "偏振度 P、消光比、布儒斯特角和相位延迟 δ",
        "pdfs": {"Monteiro_2016_Smartphone_Malus.pdf": ("The Polarization of Light and Malus' Law Using Smartphones", 2016), "Damian_2006_Real_Polarizer.pdf": ("Malus' Law for a Real Polarizer", 2006), "UCF_Photonics_Polarization.pdf": ("Photonics Laboratory Manual: Polarization", 2018)},
        "refs": [
            ("Étienne-Louis Malus",1809,"Sur une propriété de la lumière réfléchie","Mémoires de la Société d'Arcueil","马吕斯定律原始工作","https://gallica.bnf.fr/"),
            ("David Brewster",1815,"On the Laws which Regulate the Polarisation of Light by Reflexion from Transparent Bodies","Philosophical Transactions","布儒斯特定律经典论文","https://doi.org/10.1098/rstl.1815.0010"),
            ("Augustin-Jean Fresnel",1823,"Mémoire sur la double réfraction","Académie des Sciences","椭圆偏振与双折射","https://gallica.bnf.fr/"),
            ("Ioan Damian",2006,"Malus' Law for a Real Polarizer","European Journal of Physics","实际偏振片修正","https://arxiv.org/abs/physics/0604073"),
            ("M. Monteiro et al.",2016,"The Polarization of Light and Malus' Law Using Smartphones","The Physics Teacher","智能手机定量实验","https://arxiv.org/abs/1607.02659"),
            ("D. Amrani; P. Paradis",2009,"Malus's Law of Light Polarization Using a Computer-Based Laboratory","Latin-American Journal of Physics Education","自动采集与拟合","https://dialnet.unirioja.es/descarga/articulo/3689839.pdf"),
            ("University of Central Florida",2018,"Photonics Lab Manual: Polarization","CREOL","激光安全与马吕斯定律","https://photonics.creol.ucf.edu/wp-content/uploads/sites/4/2019/06/Photonics_Lab_Manual_for_High_Schools_2018.pdf"),
            ("University of Tennessee",2025,"Polarization and Birefringence Laboratory","UTK","布儒斯特角和双折射","https://labs.phys.utk.edu/mbreinig/phys421/labs/Lab10.html"),
            ("R. C. Jones",1941,"A New Calculus for the Treatment of Optical Systems","JOSA","琼斯矩阵经典工作","https://doi.org/10.1364/JOSA.31.000488"),
            ("JCGM",2008,"Guide to the Expression of Uncertainty in Measurement","BIPM","光强拟合不确定度","https://doi.org/10.59161/JCGM100-2008E"),
        ],
    },
    "michelson_wavelength": {
        "folder": "迈克尔逊干涉仪测波长", "topic": "迈克尔逊干涉仪测波长", "chapter": "第11章 波动光学",
        "routes": ["alignment", "counting", "wavelength", "uncertainty"], "method": "分振幅双光束干涉、移镜计数与位移-条纹数线性拟合", "quantity": "激光波长 λ、镜面位移 Δd、条纹计数 N 与不确定度",
        "pdfs": {"Modjtahedzadeh_2020_Interferometry.pdf": ("Wavelength and Refractive Indices from Interferometry", 2020), "MIT_Optical_Interferometer.pdf": ("Optical Interferometer Lab Guide", 2017), "MIT_Coherence_Interferometry.pdf": ("Coherence and Interferometry Laboratory", 2005)},
        "refs": [
            ("A. A. Michelson",1881,"The Relative Motion of the Earth and the Luminiferous Ether","American Journal of Science","迈克尔逊干涉仪早期经典论文","https://doi.org/10.2475/ajs.s3-22.128.120"),
            ("A. A. Michelson; E. W. Morley",1887,"On the Relative Motion of the Earth and the Luminiferous Ether","American Journal of Science","经典干涉实验","https://history.aip.org/exhibits/gap/PDF/michelson.pdf"),
            ("A. A. Michelson",1902,"Light Waves and Their Uses","University of Chicago Press","干涉测量经典专著","https://archive.org/details/lightwavesandth00michgoog"),
            ("MIT Physics",2017,"Optical Interferometer Lab Guide","MIT OpenCourseWare","光路调节与波长测量","https://ocw.mit.edu/courses/8-13-14-experimental-physics-i-ii-junior-lab-fall-2016-spring-2017/resources/mit8_13-14f16-s17expiii/"),
            ("MIT EECS",2005,"Coherence and Interferometry Laboratory","MIT OpenCourseWare","迈克尔逊相干实验","https://ocw.mit.edu/courses/6-161-modern-optics-project-laboratory-fall-2005/resources/lab2/"),
            ("K. Modjtahedzadeh",2020,"Wavelength and Refractive Indices from Interferometry","arXiv","He-Ne 波长和折射率测量","https://arxiv.org/abs/2001.02066"),
            ("B. P. Abbott et al.",2009,"LIGO: The Laser Interferometer Gravitational-Wave Observatory","Reports on Progress in Physics","精密激光干涉应用","https://doi.org/10.1088/0034-4885/72/7/076901"),
            ("NIST",2019,"SI Brochure: Realization of the Metre","NIST/BIPM","波长与长度溯源","https://www.bipm.org/en/publications/si-brochure"),
            ("JCGM",2008,"Guide to the Expression of Uncertainty in Measurement","BIPM","位移和计数不确定度","https://doi.org/10.59161/JCGM100-2008E"),
            ("PASCO Scientific",2017,"Precision Interferometer Manual","PASCO","教学仪器与回程差","https://www.pasco.com/products/lab-apparatus/light-and-optics/interferometry/os-9255a"),
        ],
    },
}


def seed_material(key: str, spec: dict) -> Path:
    root = PROJECT_ROOT / "教学素材" / "物理实验" / spec["folder"]
    ref_dir = root / "ref"; ref_dir.mkdir(parents=True, exist_ok=True)
    entries=[]
    local_by_url={}
    for filename,(title,year) in spec["pdfs"].items():
        if not (ref_dir/filename).is_file(): raise FileNotFoundError(ref_dir/filename)
        local_by_url[title]=(filename,year)
    for i,(authors,year,title,publisher,topic,url) in enumerate(spec["refs"],1):
        local = next((f"ref/{name}" for name,(pdf_title,_) in spec["pdfs"].items() if pdf_title == title), None)
        entries.append({"id":f"{key}-{i:02d}","authors":[a.strip() for a in authors.split(";")],"year":year,"title":title,"publisher":publisher,"type":"开放全文" if local else "核心题录","topic":topic,"url":url,"local_file":local})
    write_json(root/"sources.json", entries)
    write_json(root/"manifest.json", {"topic":spec["topic"],"routes":spec["routes"],"core_reference_count":10,"local_pdf_count":len(spec["pdfs"]),"method":spec["method"]})
    guide = f"# {spec['topic']}文献导读\n\n## 物理主线\n{spec['method']}。核心测量量为{spec['quantity']}。教学时应先建立理想模型，再讨论仪器零点、有限响应、读数方向、环境漂移和重复测量。\n\n## 数据处理\n四个可视化页面依次对应 {', '.join(spec['routes'])}。采用多组读数和线性或非线性拟合，报告残差、A 类与 B 类不确定度，并说明模型适用条件。\n\n## 文献使用\n经典原始工作用于追溯概念来源；高校开放实验手册用于装置、步骤和安全；现代论文用于拟合、传感器和系统误差；JCGM GUM 用于规范表达不确定度。"
    plan = f"# {spec['topic']}可视化实验方案\n\n## 实验目标\n理解{spec['method']}，完成{spec['quantity']}的测量、拟合和误差评定。\n\n## 四个页面\n" + "\n".join(f"- `/{r}`：围绕 {r} 的参数交互、曲线观察与读数训练。" for r in spec["routes"]) + "\n\n## 误差与安全\n采用单变量控制和重复测量；保持光路或气路稳定，避免视差、回程差、漏气、背景光和振动。激光实验禁止直视光束或镜面反射光。"
    atomic_write_text(root/f"{spec['topic']}文献导读.md", guide+"\n")
    atomic_write_text(root/f"{spec['topic']}可视化实验方案.md", plan+"\n")
    atomic_write_text(ref_dir/"README.md", "# 核心参考\n\n"+"\n".join(f"{i}. {x[2]} ({x[1]}), {x[5]}" for i,x in enumerate(spec["refs"],1))+"\n")
    return root


def build_one(key: str, spec: dict) -> dict:
    root=seed_material(key,spec); ref_dir=root/"ref"; rows=[]; reports=[]
    for path in [root/f"{spec['topic']}文献导读.md",root/f"{spec['topic']}可视化实验方案.md",ref_dir/"README.md"]:
        text=clean(path.read_text(encoding="utf-8")); imported=[]
        for idx,chunk in enumerate(split_chunks(text)):
            imported.append(make_row(path,1,idx,chunk,f"{spec['topic']}·教学设计","markdown",path.stem,0))
        rows.extend(imported); reports.append({"source":path.name,"source_path":relative_path(path),"source_type":"markdown","chunks":len(imported)})
    catalog=json.loads((root/"sources.json").read_text(encoding="utf-8"))
    for idx,item in enumerate(catalog):
        text=clean(f"题名：{item['title']}\n作者/机构：{'；'.join(item['authors'])}\n年份：{item['year']}\n出版者：{item['publisher']}\n主题：{item['topic']}\n权威链接：{item['url']}\n本地文件：{item['local_file'] or '仅题录，未复制受限全文'}")
        rows.append(make_row(root/"sources.json",1,idx,text,f"{spec['topic']}·核心文献题录·{item['topic']}","reference_metadata",item["title"],item["year"]))
    reports.append({"source":"sources.json","source_path":relative_path(root/"sources.json"),"source_type":"reference_metadata","references":10,"chunks":10})
    pdftotext,pdfinfo=shutil.which("pdftotext"),shutil.which("pdfinfo")
    if not pdftotext or not pdfinfo: raise RuntimeError("需要 pdftotext 和 pdfinfo")
    for filename,(title,year) in spec["pdfs"].items():
        imported,report=extract_pdf(ref_dir/filename,{"title":title,"year":year,"topic":f"{spec['topic']}·开放文献全文","pages":None,"url":next((x[5] for x in spec['refs'] if x[2]==title),"")},pdftotext,pdfinfo)
        rows.extend(imported); reports.append(report)
    manifest={"created_at":datetime.now().astimezone().isoformat(),"topic":spec["topic"],"method":spec["method"],"measured_quantity":spec["quantity"],"routes":spec["routes"],"core_references":10,"documents":len(reports),"pdf_documents":len(spec["pdfs"]),"chunks":len(rows),"output":f"agnet/knowledge_base/imports/{key}.jsonl","main_knowledge_base_modified":False,"sources":reports}
    IMPORTED_KB_DIR.mkdir(parents=True,exist_ok=True)
    atomic_write_text(IMPORTED_KB_DIR/f"{key}.jsonl","".join(json.dumps(r,ensure_ascii=False)+"\n" for r in rows))
    write_json(IMPORTED_KB_DIR/f"{key}.manifest.json",manifest); write_json(IMPORTED_KB_DIR/f"{key}.extraction_report.json",reports)
    for name in (f"{key}.jsonl",f"{key}.manifest.json",f"{key}.extraction_report.json"): shutil.copy2(IMPORTED_KB_DIR/name,root/name)
    return manifest


def build_all() -> dict:
    return {key:build_one(key,spec) for key,spec in SPECS.items()}


if __name__ == "__main__": print(json.dumps(build_all(),ensure_ascii=False,indent=2))
