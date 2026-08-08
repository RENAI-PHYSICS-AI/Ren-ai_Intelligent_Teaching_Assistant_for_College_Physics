# Git + Git LFS + GitHub 完整项目流程总结

本文总结从**新建项目、初始化 Git、配置 Git LFS、绑定 GitHub、SSH
推送、分支管理、大文件处理、历史清理**的完整流程。

适用于包含：

-   代码
-   文档
-   PDF 教材
-   PPT/PPTX 课件
-   MP4 视频
-   ZIP 数据包

的项目。

------------------------------------------------------------------------

# 一、新建项目推荐流程

## 1. 创建项目目录

推荐不要放在 OneDrive、网盘同步目录。

推荐：

    .\项目名称

原因：

-   Git 会频繁修改 `.git`
-   同步软件可能锁定文件
-   容易导致 gc、repack、prune 失败

------------------------------------------------------------------------

# 二、初始化 Git

进入项目：

``` powershell
cd .\项目名称
```

初始化：

``` powershell
git init
```

设置主分支：

``` powershell
git branch -M main
```

以后新项目默认使用 main：

``` powershell
git config --global init.defaultBranch main
```

------------------------------------------------------------------------

# 三、配置 Git LFS

安装：

``` powershell
git lfs install
```

设置需要 LFS 管理的文件：

``` powershell
git lfs track "*.pdf"
git lfs track "*.pptx"
git lfs track "*.ppt"
git lfs track "*.mp4"
git lfs track "*.zip"
git lfs track "*.exe"
```

生成：

    .gitattributes

检查：

``` powershell
type .gitattributes
```

内容：

    *.pdf filter=lfs diff=lfs merge=lfs -text
    *.pptx filter=lfs diff=lfs merge=lfs -text
    *.ppt filter=lfs diff=lfs merge=lfs -text
    *.mp4 filter=lfs diff=lfs merge=lfs -text
    *.zip filter=lfs diff=lfs merge=lfs -text
    *.exe filter=lfs diff=lfs merge=lfs -text

------------------------------------------------------------------------

# 四、配置 .gitignore

创建：

``` powershell
notepad .gitignore
```

示例：

    # Python
    __pycache__/
    *.pyc
    .venv/

    # IDE
    .vscode/

    # Node
    node_modules/

    # 临时文件
    *.tmp

    # 大文件（已使用LFS的不要写）

注意：

如果文件需要上传到 LFS：

不要写：

    *.pdf
    *.mp4

否则 Git 不会提交它们。

------------------------------------------------------------------------

# 五、第一次提交

查看状态：

``` powershell
git status
```

添加：

``` powershell
git add .
```

提交：

``` powershell
git commit -m "Initial commit"
```

检查：

``` powershell
git log --oneline
```

------------------------------------------------------------------------

# 六、创建 GitHub 仓库

在 GitHub 创建仓库。

建议：

不要勾选：

-   Add README
-   Add .gitignore
-   Add license

因为本地已经初始化。

------------------------------------------------------------------------

# 七、配置 SSH

检查 SSH：

``` powershell
ssh -T git@github.com
```

成功：

    Hi username! You've successfully authenticated

------------------------------------------------------------------------

# 八、添加远程仓库

SSH 地址：

    git@github.com:用户名/仓库名.git

添加：

``` powershell
git remote add origin git@github.com:用户名/仓库名.git
```

检查：

``` powershell
git remote -v
```

正确：

    origin git@github.com:用户名/仓库名.git

------------------------------------------------------------------------

# 九、HTTPS切换SSH

查看：

``` powershell
git remote -v
```

修改：

``` powershell
git remote set-url origin git@github.com:用户名/仓库名.git
```

确认：

``` powershell
git remote -v
```

------------------------------------------------------------------------

# 十、第一次推送

设置 main：

``` powershell
git branch -M main
```

推送：

``` powershell
git push -u origin main
```

成功：

    branch 'main' set up to track 'origin/main'

以后：

``` powershell
git push
git pull
```

------------------------------------------------------------------------

# 十一、远程已有内容导致 push 失败

错误：

    non-fast-forward

原因：

远程已有提交。

合并：

``` powershell
git pull origin main --allow-unrelated-histories
```

或者新项目直接覆盖：

``` powershell
git push -u origin main --force
```

------------------------------------------------------------------------

# 十二、分支管理

查看：

``` powershell
git branch
```

创建开发分支：

``` powershell
git switch -c develop
```

切换：

``` powershell
git switch main
```

合并：

``` powershell
git merge develop
```

删除：

``` powershell
git branch -d develop
```

------------------------------------------------------------------------

# 十三、检查 Git LFS

查看：

``` powershell
git lfs ls-files
```

应该看到：

    PDF
    PPT
    PPTX
    MP4
    ZIP

------------------------------------------------------------------------

# 十四、误提交大文件后的清理

检查大小：

``` powershell
git count-objects -vH
```

查看：

    size-pack

------------------------------------------------------------------------

## 迁移历史到 LFS

完整类型：

``` powershell
git lfs migrate import --everything --include="*.pdf,*.pptx,*.ppt,*.mp4,*.zip"
```

------------------------------------------------------------------------

## 清理历史对象

``` powershell
git reflog expire --expire=now --all
```

重新打包：

``` powershell
git repack -Ad
```

清理：

``` powershell
git prune
```

检查：

``` powershell
git count-objects -vH
```

------------------------------------------------------------------------

# 十五、查找大文件

查看 pack：

``` powershell
Get-ChildItem .git\objects\pack
```

查看大对象：

``` powershell
git verify-pack -v pack-index.idx
```

------------------------------------------------------------------------

# 十六、常见错误

## 1. curl 65 Schannel

    curl 65 schannel: server closed abruptly

原因：

HTTPS/TLS连接问题。

解决：

切换 SSH：

``` powershell
git remote set-url origin git@github.com:用户名/仓库.git
```

------------------------------------------------------------------------

## 2. pack exceeds maximum allowed size

    remote: fatal: pack exceeds maximum allowed size

原因：

历史中存在大文件。

解决：

``` powershell
git lfs migrate import --everything --include="*.pdf,*.pptx,*.ppt,*.mp4,*.zip"
```

------------------------------------------------------------------------

## 3. origin 不存在

错误：

    'origin' does not appear to be a git repository

检查：

``` powershell
git remote -v
```

添加：

``` powershell
git remote add origin 地址
```

------------------------------------------------------------------------

## 4. remote 名称错误

查看：

``` powershell
git remote
```

修改：

``` powershell
git remote rename 原名称 origin
```

------------------------------------------------------------------------

# 十七、推荐项目结构

    项目
    │
    ├── src                 Git
    ├── docs                Git
    ├── prompts             Git
    ├── config              Git
    ├── README.md           Git
    ├── .gitignore          Git
    ├── .gitattributes      Git
    │
    └── 大文件
        ├── PDF             LFS
        ├── PPT             LFS
        ├── PPTX            LFS
        ├── MP4             LFS
        └── ZIP             LFS

------------------------------------------------------------------------

# 十八、最终标准流程（一键参考）

``` powershell
git init
git branch -M main

git lfs install

git lfs track "*.pdf"
git lfs track "*.pptx"
git lfs track "*.ppt"
git lfs track "*.mp4"
git lfs track "*.zip"

git add .
git commit -m "Initial commit"

git remote add origin git@github.com:用户名/仓库名.git

git push -u origin main
```

------------------------------------------------------------------------

# 十九、维护流程

日常：

``` powershell
git add .
git commit -m "update"
git push
```

查看状态：

``` powershell
git status
```

查看 LFS：

``` powershell
git lfs ls-files
```

查看仓库大小：

``` powershell
git count-objects -vH
```
