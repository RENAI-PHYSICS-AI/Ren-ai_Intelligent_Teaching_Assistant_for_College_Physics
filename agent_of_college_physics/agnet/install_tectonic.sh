#!/usr/bin/env bash

# Install the pinned Tectonic release without root privileges, warm the package
# cache used by the teacher-exam agent, and prove that an offline/untrusted
# compilation succeeds. This script is intentionally safe to run repeatedly.

set -Eeuo pipefail
umask 077

TECTONIC_VERSION="0.16.9"
TECTONIC_URL="https://github.com/tectonic-typesetting/tectonic/releases/download/tectonic%400.16.9/tectonic-0.16.9-x86_64-unknown-linux-gnu.tar.gz"
TECTONIC_SHA256="f3c825128095dc3399ea11c08c18035b33050a216930c295c79e8eb11bd21de4"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd -P)"
RUNTIME_DIR="${PROJECT_DIR}/.runtime"
INSTALL_DIR="${RUNTIME_DIR}/tectonic"
CACHE_DIR="${RUNTIME_DIR}/tectonic-cache"
TECTONIC_BIN="${INSTALL_DIR}/tectonic"

fail() {
    printf '错误：%s\n' "$*" >&2
    exit 1
}

[[ "$(uname -s)" == "Linux" ]] || fail "本脚本仅支持 Linux。"
case "$(uname -m)" in
    x86_64|amd64) ;;
    *) fail "固定安装包仅支持 Linux x86_64，当前架构为 $(uname -m)。" ;;
esac

for required_command in curl sha256sum tar mktemp install mkdir mv rm; do
    command -v "${required_command}" >/dev/null 2>&1 \
        || fail "缺少必需命令：${required_command}"
done

install -d -m 0755 "${RUNTIME_DIR}" "${INSTALL_DIR}" "${CACHE_DIR}"
TEMP_DIR="$(mktemp -d "${RUNTIME_DIR}/.tectonic-install.XXXXXX")"

cleanup() {
    if [[ -n "${TEMP_DIR:-}" && -d "${TEMP_DIR}" ]]; then
        case "${TEMP_DIR}" in
            "${RUNTIME_DIR}"/.tectonic-install.*)
                rm -rf -- "${TEMP_DIR}"
                ;;
            *)
                printf '警告：临时目录未通过路径校验，未清理：%s\n' "${TEMP_DIR}" >&2
                ;;
        esac
    fi
}
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

ARCHIVE_PATH="${TEMP_DIR}/tectonic-${TECTONIC_VERSION}.tar.gz"
EXTRACT_DIR="${TEMP_DIR}/extract"
install -d -m 0700 "${EXTRACT_DIR}"

printf '[1/5] 下载 Tectonic %s……\n' "${TECTONIC_VERSION}"
if [[ -n "${PHYSICS_TECTONIC_ARCHIVE:-}" ]]; then
    PRELOADED_ARCHIVE="$(cd -- "$(dirname -- "${PHYSICS_TECTONIC_ARCHIVE}")" && pwd -P)/$(basename -- "${PHYSICS_TECTONIC_ARCHIVE}")"
    [[ -f "${PRELOADED_ARCHIVE}" && ! -L "${PRELOADED_ARCHIVE}" ]] \
        || fail "预下载安装包不存在或不是普通文件：${PRELOADED_ARCHIVE}"
    install -m 0600 "${PRELOADED_ARCHIVE}" "${ARCHIVE_PATH}"
else
    curl \
        --proto '=https' \
        --tlsv1.2 \
        --fail \
        --location \
        --retry 3 \
        --retry-all-errors \
        --silent \
        --show-error \
        --output "${ARCHIVE_PATH}" \
        "${TECTONIC_URL}"
fi

printf '[2/5] 严格校验发布包 SHA-256……\n'
if ! printf '%s  %s\n' "${TECTONIC_SHA256}" "${ARCHIVE_PATH}" \
    | sha256sum --check --strict --status -; then
    fail "Tectonic 发布包校验失败，拒绝安装。"
fi

# The official archive contains exactly one top-level executable. Requiring the
# exact member name also prevents absolute-path and parent-directory traversal.
[[ "$(tar -tzf "${ARCHIVE_PATH}")" == "tectonic" ]] \
    || fail "Tectonic 发布包内容与预期不符，拒绝解压。"

printf '[3/5] 安装到 %s……\n' "${TECTONIC_BIN}"
tar \
    --extract \
    --gzip \
    --file "${ARCHIVE_PATH}" \
    --directory "${EXTRACT_DIR}" \
    --no-same-owner \
    --no-same-permissions
[[ -f "${EXTRACT_DIR}/tectonic" && ! -L "${EXTRACT_DIR}/tectonic" ]] \
    || fail "发布包中没有预期的 Tectonic 可执行文件。"

install -m 0755 "${EXTRACT_DIR}/tectonic" "${INSTALL_DIR}/.tectonic.new"
"${INSTALL_DIR}/.tectonic.new" --version >/dev/null
mv -f -- "${INSTALL_DIR}/.tectonic.new" "${TECTONIC_BIN}"
printf 'Tectonic %s\n%s\n' "${TECTONIC_VERSION}" "${TECTONIC_SHA256}" \
    > "${TEMP_DIR}/RELEASE"
install -m 0644 "${TEMP_DIR}/RELEASE" "${INSTALL_DIR}/RELEASE"

WARMUP_SOURCE="${TEMP_DIR}/teacher-exam-warmup.tex"
WARMUP_DEFAULT_SOURCE="${TEMP_DIR}/teacher-exam-warmup-default.tex"
WARMUP_TEN_SOURCE="${TEMP_DIR}/teacher-exam-warmup-10.tex"
WARMUP_ELEVEN_SOURCE="${TEMP_DIR}/teacher-exam-warmup-11.tex"
WARMUP_OUTPUT="${TEMP_DIR}/warm-output"
VERIFY_OUTPUT="${TEMP_DIR}/offline-output"
install -d -m 0700 "${WARMUP_OUTPUT}" "${VERIFY_OUTPUT}"

cat > "${WARMUP_SOURCE}" <<'TEX'
\documentclass[12pt]{ctexart}
\usepackage[a4paper,margin=2cm]{geometry}
\usepackage{amsfonts,amssymb,amsthm,amsmath,mathrsfs}
\usepackage{graphicx,booktabs,longtable,array,tabularx,multirow,diagbox}
\usepackage{multicol,enumerate,enumitem,relsize,mdframed,xcolor}
\usepackage{indentfirst,ulem,calc,fancyhdr,setspace}
\usepackage[noend]{algpseudocode}
\usepackage{algorithmicx,algorithm}
\usepackage{tikz}
\usetikzlibrary{angles,arrows,arrows.meta,backgrounds,babel,calc,decorations.markings,decorations.pathmorphing,decorations.pathreplacing,fit,intersections,matrix,patterns,positioning,quotes,shapes.geometric}
\begin{document}
\section*{大学物理教研考试编译自检}
\subsection*{固定可信预热模板}
\noindent 中文试题、参考答案和评分标准均由服务器安全编译。
\textbf{本段验证粗体命令、无编号层级标题与首段不缩进。}

% Explicit Latin Modern Roman bold sizes warm lmroman8/9/10/12-bold and their TFM data.
{\fontsize{5pt}{6pt}\selectfont\rmfamily\textbf{5pt bold cache warmup: Physics.} $x_1^2\approx\mu a$\par}
{\fontsize{6pt}{7pt}\selectfont\rmfamily\textbf{6pt bold cache warmup: Physics.} $x_1^2\approx\mu a$\par}
{\fontsize{7pt}{8pt}\selectfont\rmfamily\textbf{7pt bold cache warmup: Physics.} $x_1^2\approx\mu a$\par}
{\fontsize{8pt}{10pt}\selectfont\rmfamily\textbf{8pt bold cache warmup: Physics.}\par}
{\fontsize{9pt}{11pt}\selectfont\rmfamily\textbf{9pt bold cache warmup: Physics.}\par}
{\fontsize{10pt}{12pt}\selectfont\rmfamily\textbf{10pt bold cache warmup: Physics.}\par}
{\fontsize{12pt}{14pt}\selectfont\rmfamily\textbf{12pt bold cache warmup: Physics.}\par}

\begin{enumerate}
  \item 检查 \texttt{ctexart}、\texttt{geometry} 和 \texttt{amsmath}；
  \item 检查 \verb|\section*|、\verb|\subsection*|、\verb|\textbf|、\verb|\noindent| 与列表环境。
\end{enumerate}
{\heiti 黑体标题}\quad {\songti 宋体正文}\quad {\kaishu 楷体提示}\quad {\fangsong 仿宋说明}
\begin{mdframed}
设质点做简谐振动，写出角频率与周期的关系：
\[
  \omega=2\pi f=\frac{2\pi}{T}.
\]
\[
  \sqrt{51.04}+\left[\frac{a+b}{c+d}\right]_{t_0}^{t_1},\qquad a\approx\mu b.
\]
\end{mdframed}
\begin{multicols}{2}
试题文件：\texttt{main.tex}
\columnbreak
答案文件：\texttt{answer.tex}
\end{multicols}
\begin{center}
\begin{tikzpicture}[>=Stealth,scale=0.9]
  \draw[->] (-0.2,0) -- (2.4,0) node[right] {$x$};
  \draw[->] (0,-0.2) -- (0,1.8) node[above] {$y$};
  \draw[thick,blue] (0.2,0.3) -- (1.8,1.2);
  \draw[->,red] (1,0.75) -- (1.7,0.75) node[right] {$\vec F$};
  \node[draw,circle,inner sep=2pt] at (1,0.75) {$m$};
\end{tikzpicture}
\end{center}
\begin{tabularx}{\textwidth}{@{}lX@{}}
\toprule
项目 & 验证内容 \\
\midrule
中文 & ctex 与内置中文字体 \\
公式 & amsmath 与 amssymb \\
版式 & geometry、表格、分栏与边框 \\
\bottomrule
\end{tabularx}
\end{document}
TEX

cat > "${WARMUP_TEN_SOURCE}" <<'TEX'
\documentclass[10pt]{ctexart}
\usepackage[a4paper,margin=2cm]{geometry}
\usepackage{times}
\usepackage{amsfonts,amssymb,amsthm,amsmath,mathrsfs}
\usepackage{graphicx,booktabs,longtable,array,tabularx,multirow,diagbox}
\usepackage{multicol,enumerate,enumitem,relsize,mdframed,xcolor}
\usepackage{indentfirst,ulem,calc,fancyhdr,setspace}
\usepackage[noend]{algpseudocode}
\usepackage{algorithmicx,algorithm}
\begin{document}
十号中文试卷与参考答案编译资源自检。
\[E_k=\frac{1}{2}mv^2,\qquad \omega=\frac{2\pi}{T}.\]
\end{document}
TEX

cat > "${WARMUP_DEFAULT_SOURCE}" <<'TEX'
\documentclass{ctexart}
\usepackage[a4paper,margin=2cm]{geometry}
\usepackage{times}
\usepackage{amsfonts,amssymb,amsthm,amsmath,mathrsfs}
\usepackage{graphicx,booktabs,longtable,array,tabularx,multirow,diagbox}
\usepackage{multicol,enumerate,enumitem,relsize,mdframed,xcolor}
\usepackage{indentfirst,ulem,calc,fancyhdr,setspace}
\usepackage[noend]{algpseudocode}
\usepackage{algorithmicx,algorithm}
\begin{document}
默认字号中文试卷与参考答案编译资源自检。
\[E_k=\frac{1}{2}mv^2,\qquad \omega=\frac{2\pi}{T}.\]
\end{document}
TEX

cat > "${WARMUP_ELEVEN_SOURCE}" <<'TEX'
\documentclass[11pt]{article}
\usepackage[UTF8]{ctex}
\usepackage[a4paper,margin=2cm]{geometry}
\usepackage{times}
\usepackage{amsfonts,amssymb,amsthm,amsmath,mathrsfs}
\usepackage{graphicx,booktabs,longtable,array,tabularx,multirow,diagbox}
\usepackage{multicol,enumerate,enumitem,relsize,mdframed,xcolor}
\usepackage{indentfirst,ulem,calc,fancyhdr,setspace}
\usepackage[noend]{algpseudocode}
\usepackage{algorithmicx,algorithm}
\begin{document}
十一号中文试卷编译资源自检。
\[E_k=\frac{1}{2}mv^2,\qquad \omega=\frac{2\pi}{T}.\]
\end{document}
TEX

# Only these fixed, embedded warmup documents may use the network-backed
# bundle. Model-produced TeX is compiled elsewhere with --only-cached.
printf '[4/5] 用固定可信模板预热 ctex、TikZ、粗体字号与试卷依赖缓存……\n'
for source in "${WARMUP_SOURCE}" "${WARMUP_DEFAULT_SOURCE}" "${WARMUP_TEN_SOURCE}" "${WARMUP_ELEVEN_SOURCE}"; do
    TECTONIC_UNTRUSTED_MODE=1 \
    XDG_CACHE_HOME="${CACHE_DIR}" \
    "${TECTONIC_BIN}" -X compile \
        --untrusted \
        --outdir "${WARMUP_OUTPUT}" \
        "${source}"
done
for name in teacher-exam-warmup teacher-exam-warmup-default teacher-exam-warmup-10 teacher-exam-warmup-11; do
    [[ -s "${WARMUP_OUTPUT}/${name}.pdf" ]] \
        || fail "联网预热编译未生成 ${name}.pdf。"
done

printf '[5/5] 验证只读缓存模式下的安全编译……\n'
for source in "${WARMUP_SOURCE}" "${WARMUP_DEFAULT_SOURCE}" "${WARMUP_TEN_SOURCE}" "${WARMUP_ELEVEN_SOURCE}"; do
    TECTONIC_UNTRUSTED_MODE=1 \
    XDG_CACHE_HOME="${CACHE_DIR}" \
    "${TECTONIC_BIN}" -X compile \
        --untrusted \
        --only-cached \
        --outdir "${VERIFY_OUTPUT}" \
        "${source}"
done
for name in teacher-exam-warmup teacher-exam-warmup-default teacher-exam-warmup-10 teacher-exam-warmup-11; do
    [[ -s "${VERIFY_OUTPUT}/${name}.pdf" ]] \
        || fail "--only-cached 安全编译未生成 ${name}.pdf。"
done

printf '\n安装与验证完成。\n'
printf '  可执行文件：%s\n' "${TECTONIC_BIN}"
printf '  依赖缓存：  %s\n' "${CACHE_DIR}"
printf '  运行策略：  --untrusted --only-cached\n'
