# -*- coding: utf-8 -*-
"""prototype_section.py —— 平面截正方体解析求交与截面边数验证原型。"""
import math

def cube_section_vertices(normal, d, a=1.0):
    """求平面 n·x = d 与 [-a/2, a/2]^3 正方体 12 条棱的交点。"""
    nx, ny, nz = normal
    h = a / 2.0
    verts = [
        (sx * h, sy * h, sz * h)
        for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)
    ]
    edges = []
    for i in range(8):
        for j in range(i + 1, 8):
            diff = sum(1 for k in range(3) if verts[i][k] != verts[j][k])
            if diff == 1:
                edges.append((verts[i], verts[j]))
    pts = []
    for p1, p2 in edges:
        v1 = nx * p1[0] + ny * p1[1] + nz * p1[2] - d
        v2 = nx * p2[0] + ny * p2[1] + nz * p2[2] - d
        if abs(v1) < 1e-9:
            pts.append(p1)
        elif abs(v2) < 1e-9:
            pts.append(p2)
        elif v1 * v2 < 0:
            t = v1 / (v1 - v2)
            pts.append(tuple(p1[k] + t * (p2[k] - p1[k]) for k in range(3)))
    uniq = []
    for p in pts:
        if not any(math.dist(p, q) < 1e-6 for q in uniq):
            uniq.append(p)
    return uniq

if __name__ == "__main__":
    pts = cube_section_vertices((1, 1, 1), 0.0)
    print("过中心且垂直体对角线截面顶点数：", len(pts))
