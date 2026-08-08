from __future__ import annotations

import ast
import io
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import imageio.v2 as imageio
import numpy as np
import plotly.graph_objects as go
import streamlit as st
from PIL import Image, ImageDraw, ImageFont


_VIZ_PATTERN = re.compile(r"<!--\s*PHYSICS_VIZ:(.*?)-->", re.DOTALL)
_FUNCTIONS = {
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "asin": math.asin,
    "acos": math.acos,
    "atan": math.atan,
    "sinh": math.sinh,
    "cosh": math.cosh,
    "exp": math.exp,
    "log": math.log,
    "log10": math.log10,
    "sqrt": math.sqrt,
    "abs": abs,
}
_CONSTANTS = {"pi": math.pi, "e": math.e}
_ALLOWED_NODES = (
    ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant, ast.Name, ast.Load,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.Mod, ast.UAdd, ast.USub,
    ast.Call,
)


def _cjk_font_path() -> Path | None:
    """Locate a Chinese-capable font on Windows, macOS, Debian and Rocky Linux."""
    configured = os.getenv("PHYSICS_CJK_FONT", "").strip()
    windows_root = os.getenv("WINDIR", "").strip()
    candidates = [
        Path(configured).expanduser() if configured else None,
        Path(windows_root) / "Fonts" / "msyh.ttc" if windows_root else None,
        Path("/System/Library/Fonts/PingFang.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/google-noto-cjk-fonts/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/google-noto-vf/NotoSansCJK-VF.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    for candidate in candidates:
        if candidate is not None and candidate.is_file():
            return candidate
    matcher = shutil.which("fc-match")
    if matcher:
        try:
            matched = subprocess.run(
                [matcher, "-f", "%{file}\n", "Noto Sans CJK SC"],
                check=True,
                capture_output=True,
                text=True,
                timeout=5,
            ).stdout.splitlines()
            if matched and Path(matched[0]).is_file():
                return Path(matched[0])
        except (OSError, subprocess.SubprocessError):
            pass
    return None


def extract_visualizations(text: str) -> tuple[str, list[dict[str, Any]]]:
    """Remove hidden visualization specs from model text and parse valid JSON."""
    specs: list[dict[str, Any]] = []
    for match in _VIZ_PATTERN.finditer(text):
        try:
            spec = json.loads(match.group(1).strip())
            if isinstance(spec, dict) and spec.get("kind") in {"function", "parametric", "animation", "data"}:
                specs.append(spec)
        except (json.JSONDecodeError, TypeError):
            continue
    cleaned = _VIZ_PATTERN.sub("", text).rstrip()
    return cleaned, specs[:3]


def apply_requested_media_format(specs: list[dict], question: str) -> list[dict]:
    """Force animation/media semantics even when the local model returns a static chart."""
    compact = question.lower().replace(" ", "")
    wants_gif = "gif" in compact or "动图" in compact
    wants_mp4 = "mp4" in compact or "视频" in compact
    wants_animation = wants_gif or wants_mp4 or any(
        word in compact for word in ("动画", "动态演示", "运动演示")
    )
    requested = (
        "both" if wants_gif and wants_mp4 else
        "gif" if wants_gif else "mp4" if wants_mp4 else "interactive"
    )
    for spec in specs:
        kind = spec.get("kind")
        if wants_animation and kind == "function":
            parameter = "x"
            converted_series = []
            for item in spec.get("series", []):
                if not isinstance(item, dict) or not item.get("expression"):
                    continue
                converted_series.append({
                    "name": item.get("name", "运动点"),
                    "x_expression": parameter,
                    "y_expression": item["expression"],
                })
            if converted_series:
                spec["kind"] = "animation"
                spec["parameter"] = parameter
                spec["min"] = float(spec.get("x_min", -10))
                spec["max"] = float(spec.get("x_max", 10))
                spec["series"] = converted_series
                kind = "animation"
        elif wants_animation and kind == "parametric":
            spec["kind"] = "animation"
            kind = "animation"
        if kind == "animation":
            spec["output_format"] = requested
    return specs


def _compile_expression(expression: str, variable: str):
    if not isinstance(expression, str) or len(expression) > 200:
        raise ValueError("表达式过长或格式无效")
    tree = ast.parse(expression.replace("^", "**"), mode="eval")
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise ValueError("表达式包含不允许的语法")
        if isinstance(node, ast.Name) and node.id not in {*_FUNCTIONS, *_CONSTANTS, variable}:
            raise ValueError(f"不允许的名称：{node.id}")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in _FUNCTIONS or len(node.args) != 1:
                raise ValueError("仅允许单参数数学函数")
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Pow):
            if isinstance(node.right, ast.Constant) and abs(float(node.right.value)) > 12:
                raise ValueError("指数超出安全范围")
    return compile(tree, "<physics-visualization>", "eval")


def _values(expression: str, variable: str, inputs: list[float]) -> list[float | None]:
    code = _compile_expression(expression, variable)
    values: list[float | None] = []
    base = {**_FUNCTIONS, **_CONSTANTS}
    for value in inputs:
        try:
            result = float(eval(code, {"__builtins__": {}}, {**base, variable: value}))
            values.append(result if math.isfinite(result) and abs(result) < 1e100 else None)
        except (ArithmeticError, ValueError, TypeError, OverflowError):
            values.append(None)
    return values


def _sample(start: float, end: float, count: int = 320) -> list[float]:
    if not math.isfinite(start) or not math.isfinite(end) or start >= end or end - start > 1e6:
        raise ValueError("绘图区间无效")
    return [start + (end - start) * index / (count - 1) for index in range(count)]


def _figure(spec: dict[str, Any]) -> go.Figure:
    kind = spec["kind"]
    series = spec.get("series")
    if not isinstance(series, list) or not series:
        raise ValueError("缺少绘图序列")
    figure = go.Figure()
    for index, item in enumerate(series[:6]):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or f"序列{index + 1}")[:60]
        if kind == "function":
            x_values = _sample(float(spec.get("x_min", -10)), float(spec.get("x_max", 10)))
            y_values = _values(str(item.get("expression", "")), "x", x_values)
        elif kind in {"parametric", "animation"}:
            parameter = str(spec.get("parameter") or "t")
            if not parameter.isidentifier() or len(parameter) > 12:
                raise ValueError("参数名称无效")
            parameters = _sample(float(spec.get("min", 0)), float(spec.get("max", 2 * math.pi)))
            x_values = _values(str(item.get("x_expression", "")), parameter, parameters)
            y_values = _values(str(item.get("y_expression", "")), parameter, parameters)
        else:
            raw_x, raw_y = item.get("x", []), item.get("y", [])
            if not isinstance(raw_x, list) or not isinstance(raw_y, list) or len(raw_x) != len(raw_y):
                raise ValueError("数据序列长度不一致")
            x_values = [float(value) for value in raw_x[:1000]]
            y_values = [float(value) for value in raw_y[:1000]]
        if kind == "animation":
            figure.add_trace(go.Scatter(
                x=x_values, y=y_values, mode="lines", name=f"{name} 轨迹",
                line=dict(dash="dot"), opacity=0.55,
            ))
            figure.add_trace(go.Scatter(
                x=[x_values[0]], y=[y_values[0]], mode="markers", name=name,
                marker=dict(size=14),
            ))
        else:
            mode = "markers+lines" if item.get("markers") else "lines"
            figure.add_trace(go.Scatter(x=x_values, y=y_values, mode=mode, name=name))
    if kind == "animation":
        parameters = _sample(float(spec.get("min", 0)), float(spec.get("max", 2 * math.pi)), 120)
        animated_series = []
        for item in series[:6]:
            parameter = str(spec.get("parameter") or "t")
            animated_series.append((
                _values(str(item.get("x_expression", "")), parameter, parameters),
                _values(str(item.get("y_expression", "")), parameter, parameters),
            ))
        marker_trace_indexes = [2 * index + 1 for index in range(len(animated_series))]
        figure.frames = [
            go.Frame(
                data=[go.Scatter(x=[x_values[frame_index]], y=[y_values[frame_index]])
                      for x_values, y_values in animated_series],
                traces=marker_trace_indexes,
                name=str(frame_index),
            )
            for frame_index in range(len(parameters))
        ]
        figure.update_layout(
            updatemenus=[dict(
                type="buttons", direction="left", x=0, y=1.16,
                buttons=[
                    dict(label="▶ 播放", method="animate", args=[None, {
                        "frame": {"duration": 45, "redraw": False},
                        "transition": {"duration": 0}, "fromcurrent": True,
                    }]),
                    dict(label="Ⅱ 暂停", method="animate", args=[[None], {
                        "frame": {"duration": 0, "redraw": False},
                        "mode": "immediate", "transition": {"duration": 0},
                    }]),
                ],
            )],
            sliders=[dict(
                currentvalue={"prefix": f"{str(spec.get('parameter') or 't')} = "},
                steps=[dict(label=f"{value:.2f}", method="animate", args=[[str(index)], {
                    "mode": "immediate", "frame": {"duration": 0, "redraw": False},
                    "transition": {"duration": 0},
                }]) for index, value in enumerate(parameters)],
            )],
        )
    figure.update_layout(
        title=str(spec.get("title") or "物理量可视化")[:100],
        xaxis_title=str(spec.get("x_label") or "x")[:60],
        yaxis_title=str(spec.get("y_label") or "y")[:60],
        hovermode="x unified",
        margin=dict(l=35, r=25, t=60, b=35),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return figure


def _python_demo(spec: dict[str, Any]) -> str:
    """Generate readable Plotly code equivalent to the validated chart spec."""
    kind = spec["kind"]
    lines = [
        "import numpy as np",
        "import plotly.graph_objects as go",
        "from numpy import sin, cos, tan, exp, log, log10, sqrt, abs, pi, e",
        "",
        "fig = go.Figure()",
    ]
    for index, item in enumerate(spec.get("series", [])[:6]):
        name = str(item.get("name") or f"序列{index + 1}")[:60]
        if kind == "function":
            start, end = float(spec.get("x_min", -10)), float(spec.get("x_max", 10))
            expression = str(item.get("expression", "")).replace("^", "**")
            lines.extend([
                f"x = np.linspace({start!r}, {end!r}, 320)",
                f"y = {expression}",
                f"fig.add_scatter(x=x, y=y, mode='lines', name={name!r})",
            ])
        elif kind in {"parametric", "animation"}:
            parameter = str(spec.get("parameter") or "t")
            start, end = float(spec.get("min", 0)), float(spec.get("max", 2 * math.pi))
            x_expression = str(item.get("x_expression", "")).replace("^", "**")
            y_expression = str(item.get("y_expression", "")).replace("^", "**")
            lines.extend([
                f"{parameter} = np.linspace({start!r}, {end!r}, 320)",
                f"x = {x_expression}",
                f"y = {y_expression}",
                (f"fig.add_scatter(x=x, y=y, mode='lines', name={name!r})"
                 if kind == "parametric" else
                 f"fig.add_scatter(x=x, y=y, mode='lines', name={name!r} + ' 轨迹')"),
            ])
        else:
            x_values = [float(value) for value in item.get("x", [])[:1000]]
            y_values = [float(value) for value in item.get("y", [])[:1000]]
            lines.extend([
                f"x = {x_values!r}",
                f"y = {y_values!r}",
                f"fig.add_scatter(x=x, y=y, mode='lines+markers', name={name!r})",
            ])
    title = str(spec.get("title") or "物理量可视化")[:100]
    x_label = str(spec.get("x_label") or "x")[:60]
    y_label = str(spec.get("y_label") or "y")[:60]
    lines.extend([
        "",
        f"fig.update_layout(title={title!r}, xaxis_title={x_label!r}, yaxis_title={y_label!r})",
        "fig.show()",
    ])
    if kind == "animation":
        lines[-2:-2] = [
            "# 应用运行时会将参数序列转换为 Plotly 帧，并添加播放、暂停和进度控制。",
        ]
    return "\n".join(lines)


def _animation_frames(spec: dict[str, Any], count: int = 96) -> list[Image.Image]:
    """Render validated animation expressions to portable raster frames."""
    parameter = str(spec.get("parameter") or "t")
    parameters = _sample(float(spec.get("min", 0)), float(spec.get("max", 2 * math.pi)), count)
    paths = []
    for item in spec.get("series", [])[:6]:
        if not isinstance(item, dict):
            continue
        paths.append((
            str(item.get("name") or "motion")[:40],
            _values(str(item.get("x_expression", "")), parameter, parameters),
            _values(str(item.get("y_expression", "")), parameter, parameters),
        ))
    finite_x = [value for _, xs, _ in paths for value in xs if value is not None]
    finite_y = [value for _, _, ys in paths for value in ys if value is not None]
    if not finite_x or not finite_y:
        raise ValueError("动画没有可绘制的有限数值")
    x_min, x_max = min(finite_x), max(finite_x)
    y_min, y_max = min(finite_y), max(finite_y)
    if math.isclose(x_min, x_max):
        x_min, x_max = x_min - 1, x_max + 1
    if math.isclose(y_min, y_max):
        y_min, y_max = y_min - 1, y_max + 1
    x_pad, y_pad = (x_max - x_min) * 0.1, (y_max - y_min) * 0.16
    x_min, x_max = x_min - x_pad, x_max + x_pad
    y_min, y_max = y_min - y_pad, y_max + y_pad
    width, height, margin = 720, 404, 48
    plot_width, plot_height = width - 2 * margin, height - 2 * margin
    colors = ["#55b8ff", "#ff9f43", "#5ee6a8", "#d58cff", "#ff6b81", "#ffd166"]

    def point(x_value: float, y_value: float) -> tuple[int, int]:
        px = margin + int((x_value - x_min) / (x_max - x_min) * plot_width)
        py = height - margin - int((y_value - y_min) / (y_max - y_min) * plot_height)
        return px, py

    font_path = _cjk_font_path()
    font = ImageFont.truetype(str(font_path), 20) if font_path else ImageFont.load_default()
    small_font = ImageFont.truetype(str(font_path), 15) if font_path else ImageFont.load_default()
    frames = []
    for frame_index, parameter_value in enumerate(parameters):
        image = Image.new("RGB", (width, height), "#101923")
        draw = ImageDraw.Draw(image)
        for grid_index in range(6):
            x = margin + int(plot_width * grid_index / 5)
            y = margin + int(plot_height * grid_index / 5)
            draw.line((x, margin, x, height - margin), fill="#263847", width=1)
            draw.line((margin, y, width - margin, y), fill="#263847", width=1)
        if x_min <= 0 <= x_max:
            axis_x, _ = point(0, y_min)
            draw.line((axis_x, margin, axis_x, height - margin), fill="#6f8293", width=2)
        if y_min <= 0 <= y_max:
            _, axis_y = point(x_min, 0)
            draw.line((margin, axis_y, width - margin, axis_y), fill="#6f8293", width=2)
        for series_index, (name, x_values, y_values) in enumerate(paths):
            color = colors[series_index % len(colors)]
            path_points = [
                point(x_value, y_value)
                for x_value, y_value in zip(x_values, y_values)
                if x_value is not None and y_value is not None
            ]
            if len(path_points) > 1:
                draw.line(path_points, fill=color, width=2)
            x_value, y_value = x_values[frame_index], y_values[frame_index]
            if x_value is not None and y_value is not None:
                px, py = point(x_value, y_value)
                draw.ellipse((px - 8, py - 8, px + 8, py + 8), fill=color, outline="white", width=2)
                draw.text((margin + series_index * 145, height - 33), name, fill=color, font=small_font)
        title = str(spec.get("title") or "Physics animation")[:60]
        draw.text((margin, 13), title, fill="#f1f6fa", font=font)
        draw.text((width - 175, 17), f"{parameter} = {parameter_value:.2f}", fill="#b8c7d3", font=small_font)
        frames.append(image)
    return frames


@st.cache_data(show_spinner=False, max_entries=16)
def _animation_media(spec_json: str, output_format: str) -> bytes:
    spec = json.loads(spec_json)
    frames = _animation_frames(spec)
    if output_format == "gif":
        buffer = io.BytesIO()
        frames[0].save(
            buffer, format="GIF", save_all=True, append_images=frames[1:],
            duration=45, loop=0, optimize=False,
        )
        return buffer.getvalue()
    temporary_path = ""
    try:
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as temporary:
            temporary_path = temporary.name
        with imageio.get_writer(
            temporary_path, fps=24, codec="libx264", quality=7, macro_block_size=2
        ) as writer:
            for frame in frames:
                writer.append_data(np.asarray(frame))
        return Path(temporary_path).read_bytes()
    finally:
        if temporary_path:
            Path(temporary_path).unlink(missing_ok=True)


def render_visualizations(specs: list[dict[str, Any]]) -> None:
    for index, spec in enumerate(specs):
        try:
            figure = _figure(spec)
            st.markdown("**可视化代码**")
            st.code(_python_demo(spec), language="python")
            with st.container(border=True):
                st.markdown("#### ▶ 运行演示")
                st.caption("代码已在受限的可视化环境中运行，可缩放、悬停查看数值或切换曲线。")
                st.plotly_chart(
                    figure,
                    key=f"physics_viz_{index}_{abs(hash(json.dumps(spec, sort_keys=True, ensure_ascii=False)))}",
                    width="stretch",
                    config={"displaylogo": False, "responsive": True},
                    theme="streamlit",
                )
                if spec.get("kind") == "animation":
                    requested_format = str(spec.get("output_format") or "interactive").lower()
                    formats = []
                    if requested_format in {"gif", "both"}:
                        formats.append("gif")
                    if requested_format in {"mp4", "both"}:
                        formats.append("mp4")
                    for media_format in formats:
                        st.markdown(f"#### {media_format.upper()} 动画")
                        with st.spinner(f"正在生成 {media_format.upper()} 动画……"):
                            media = _animation_media(
                                json.dumps(spec, ensure_ascii=False, sort_keys=True), media_format
                            )
                        if media_format == "gif":
                            st.image(media)
                            mime = "image/gif"
                        else:
                            st.video(media, format="video/mp4")
                            mime = "video/mp4"
                        st.download_button(
                            f"下载 {media_format.upper()}", data=media,
                            file_name=f"physics_animation.{media_format}", mime=mime,
                            key=f"physics_media_{media_format}_{index}_{abs(hash(json.dumps(spec, sort_keys=True, ensure_ascii=False)))}",
                            use_container_width=True,
                        )
        except Exception as exc:
            st.warning(f"可视化生成失败：{exc}")
