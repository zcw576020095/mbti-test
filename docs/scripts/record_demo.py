#!/usr/bin/env python3
"""录制 README 顶部的演示 GIF。

帧走 CDP 的 Page.startScreencast(format=png)，**不要用 Playwright 的录像**：
录像编码成 VP8 是有损的，纯色块会出现块效应、字形边缘发毛，就是"动图模糊、
颜色不对"的真正原因（和输出缩放、调色板大小都无关）。screencast 的 PNG 帧无损。

GIF 由 Pillow 合成：Playwright 自带的 ffmpeg 是 --disable-everything 编的，
没有 gif muxer 也没有 palettegen 滤镜，标准那套 -vf fps=..,palettegen 一律失败。

用法：
    mbti-test-venv/bin/python docs/scripts/record_demo.py
    mbti-test-venv/bin/python docs/scripts/record_demo.py --keep-frames
    mbti-test-venv/bin/python docs/scripts/record_demo.py --from-frames /tmp/xxx
"""

import argparse
import base64
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / 'docs' / 'images'
PY = ROOT / 'mbti-test-venv' / 'bin' / 'python'
CHROMIUM = (Path.home() / 'Library/Caches/ms-playwright/chromium-1194'
            / 'chrome-mac/Chromium.app/Contents/MacOS/Chromium')

BASE = 'http://127.0.0.1:8000'
DEMO_USER, DEMO_PASSWORD = 'demo_mbti', 'Demo#2026mbti'

# 录制视口。1280 是内容不被横向挤压的下限；README 按 width="820" 引用，
# 等于 1.56 倍像素密度，Retina 上更锐利。缩小源图就是永久丢像素（上一版
# 740 源被放大到 820，这才是糊的主因）。
VIEW_W, VIEW_H = 1280, 800

CURSOR_JS = r"""
(() => {
  if (window.__demoCursor) return;
  window.__demoCursor = true;
  const add = () => {
    if (!document.body) return;
    const dot = document.createElement('div');
    dot.id = '__cursor';
    dot.style.cssText = [
      'position:fixed', 'z-index:2147483647', 'left:0', 'top:0',
      'width:18px', 'height:18px', 'margin:-9px 0 0 -9px',
      'border-radius:50%', 'pointer-events:none',
      'background:rgba(255,255,255,.95)',
      'box-shadow:0 0 0 2px rgba(102,126,234,.95), 0 2px 10px rgba(0,0,0,.35)',
      'transition:transform .08s ease-out', 'opacity:0',
    ].join(';');
    document.body.appendChild(dot);
    document.addEventListener('mousemove', (e) => {
      dot.style.opacity = '1';
      dot.style.transform = `translate(${e.clientX}px, ${e.clientY}px)`;
    }, true);
    document.addEventListener('mousedown', (e) => {
      const r = document.createElement('div');
      r.style.cssText = [
        'position:fixed', 'z-index:2147483646', 'pointer-events:none',
        `left:${e.clientX}px`, `top:${e.clientY}px`,
        'width:14px', 'height:14px', 'margin:-7px 0 0 -7px',
        'border-radius:50%', 'border:2px solid rgba(102,126,234,.95)',
      ].join(';');
      document.body.appendChild(r);
      r.animate(
        [{ transform: 'scale(1)', opacity: 1 },
         { transform: 'scale(3.6)', opacity: 0 }],
        { duration: 480, easing: 'ease-out' },
      ).onfinish = () => r.remove();
    }, true);
  };
  if (document.body) add();
  else document.addEventListener('DOMContentLoaded', add);
})();
"""

# 演示账号的准备在子进程里做（需要 django setup），录制主流程只管点页面。
# 关键：密码只在录制**开始前**设置一次。中途改密码会轮换 password hash，
# Django 的 session auth hash 随之失效，浏览器会被静默登出 —— 表现是录到
# 一半跳回登录页，而不是报错。
PREP_SNIPPET = r'''
import os, sys, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mbti_site.settings')
django.setup()
from django.contrib.auth.models import User
from mbti.models import Question, Response, Result, Questionnaire
from mbti.services_standard import StandardMBTIScoringService as S

username, password, mode = sys.argv[1], sys.argv[2], sys.argv[3]
user, created = User.objects.get_or_create(username=username)
# set_password 只在录制**开始前**（mode=answered）做。录制中途改密码会轮换
# password hash，Django 的 session auth hash 随之失效，浏览器被静默登出 ——
# 表现是后半段跳回登录页，不报错。我在这上面栽过一次。
if mode == 'answered' or created:
    user.set_password(password)
    user.save()

q = Questionnaire.objects.filter(key='mbti_standard_93').first()
questions = list(Question.objects.filter(questionnaire=q).order_by('id'))
Response.objects.filter(user=user).delete()
Result.objects.filter(user=user).delete()

if mode == 'answered':
    # 预填前 N 页之外的全部作答，让录制只演示"最后一页 + 提交"这一小段，
    # 否则要点满 93 题，成片会长到没人看。
    for idx, qq in enumerate(questions):
        if idx < 10:      # 第 1 页留空，录制时现场点
            continue
        Response.objects.create(user=user, question=qq, choice=1, questionnaire=q)

if mode == 'result':
    for qq in questions:
        Response.objects.create(user=user, question=qq, choice=1, questionnaire=q)
    responses = Response.objects.filter(user=user).select_related('question')
    dims, counts = S.calculate_scores_standard(responses)
    code = S.generate_type_code_standard(dims)
    Result.objects.update_or_create(
        user=user, defaults={'type_code': code, 'score_detail': dims,
                             'confidence': {}, 'questionnaire': q})
    print('result:', code)
print('ok', Response.objects.filter(user=user).count())
'''


def prep(mode):
    """在 django 环境里准备演示数据。录制过程中绝不调用（会踢掉登录态）。"""
    out = subprocess.run([str(PY), '-c', PREP_SNIPPET, DEMO_USER, DEMO_PASSWORD, mode],
                         cwd=str(ROOT), capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(f'准备数据失败：\n{out.stdout}\n{out.stderr}')
    return out.stdout.strip()


def glide(page, x, y, steps=18):
    """插值移动鼠标，让注入的光标看得出轨迹（直接 click 会瞬移）。"""
    state = page.evaluate('() => { const d = document.getElementById("__cursor");'
                          ' return d ? d.style.transform : ""; }')
    m = re.findall(r'-?[\d.]+', state or '')
    cx, cy = (float(m[0]), float(m[1])) if len(m) >= 2 else (VIEW_W / 2, VIEW_H / 2)
    for i in range(1, steps + 1):
        t = i / steps
        ease = 1 - (1 - t) ** 3
        page.mouse.move(cx + (x - cx) * ease, cy + (y - cy) * ease)
        page.wait_for_timeout(9)


def click(page, locator, settle=380):
    locator.scroll_into_view_if_needed()
    box = locator.bounding_box()
    if not box:
        raise RuntimeError('元素没有 bounding box，可能被遮住了')
    glide(page, box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
    page.wait_for_timeout(110)
    locator.click()
    page.wait_for_timeout(settle)


def smooth_scroll(page, to, steps=22, pause=26):
    """匀速滚到指定位置。一次 scrollTo 是瞬移，动图里看着像跳帧。"""
    cur = page.evaluate('() => window.scrollY')
    for i in range(1, steps + 1):
        t = i / steps
        ease = 1 - (1 - t) ** 3
        page.evaluate(f'() => window.scrollTo(0, {cur + (to - cur) * ease})')
        page.wait_for_timeout(pause)


def login(page):
    """登录页的 id 是 username / login_password，不是 Django 默认的 id_xxx。"""
    page.goto(f'{BASE}/users/login/', wait_until='networkidle')
    page.wait_for_timeout(600)
    page.fill('input[name="username"]', DEMO_USER)
    page.wait_for_timeout(200)
    page.fill('input[name="password"]', DEMO_PASSWORD)
    page.wait_for_timeout(300)
    click(page, page.locator('button[type="submit"]'), settle=1200)
    page.wait_for_load_state('networkidle')


def answer_visible(page, count=4):
    """点当前页的前 count 题。

    radio 是 opacity:0 / width:0 的隐藏输入，直接点它什么也不会发生（也不报错）。
    必须点包着它的 label.option-card —— 页面的 JS 监听的就是 card 的 click。
    """
    cards = page.locator('label.option-card')
    total = cards.count()
    if total < 2:
        raise RuntimeError(f'当前页只找到 {total} 个 option-card，选择器或页面不对')
    for i in range(count):
        idx = i * 2 + (i % 2)      # 交替选 A / B，别一路点同一侧
        if idx >= total:
            break
        click(page, cards.nth(idx), settle=240)
        if i == 1:
            smooth_scroll(page, 400, steps=10)


class Screencast:
    """CDP Page.startScreencast(format=png) 的帧收集器。

    必须显式给 maxWidth/maxHeight，否则 CDP 会自行缩放输出，又回到糊字问题。
    """

    def __init__(self, ctx, page, frame_dir):
        self.dir = frame_dir
        self.paths = []
        self._t0 = time.time()
        self._client = ctx.new_cdp_session(page)
        self._client.on('Page.screencastFrame', self._on_frame)
        self._client.send('Page.startScreencast', {
            'format': 'png', 'everyNthFrame': 1,
            'maxWidth': VIEW_W, 'maxHeight': VIEW_H,
        })

    def _on_frame(self, params):
        path = self.dir / f'{len(self.paths):05d}.png'
        path.write_bytes(base64.b64decode(params['data']))
        self.paths.append(path)
        try:
            # 不 Ack 的话 Chromium 会停发后续帧
            self._client.send('Page.screencastFrameAck',
                              {'sessionId': params['sessionId']})
        except Exception:
            pass

    def stop(self):
        self._elapsed = time.time() - self._t0
        try:
            self._client.send('Page.stopScreencast')
        except Exception:
            pass

    @property
    def fps(self):
        el = getattr(self, '_elapsed', None) or (time.time() - self._t0)
        return len(self.paths) / el if el else 0


def record(frame_dir):
    """跑一遍演示流程，把 PNG 帧写进 frame_dir，返回 (帧路径, 实测帧率)。"""
    from playwright.sync_api import sync_playwright

    prep('answered')
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=str(CHROMIUM))
        ctx = browser.new_context(viewport={'width': VIEW_W, 'height': VIEW_H},
                                  device_scale_factor=1)
        ctx.add_init_script(CURSOR_JS)
        page = ctx.new_page()

        # 先把首页打开、字体和图片都加载完，再开始录 —— 否则首帧是白屏，
        # 而 GitHub 拿首帧当封面。
        page.goto(f'{BASE}/', wait_until='networkidle')
        page.wait_for_timeout(1500)

        cast = Screencast(ctx, page, frame_dir)
        try:
            # 滚动是体积大头：滚的时候整屏都在变，GIF 的帧间压缩完全吃不到。
            # 所以每处只滚一段、步数给少些，把预算留给"点选项/出结果"这些
            # 真正要看清的画面。别靠缩小输出尺寸省体积，那是拿锐度换。

            # ① 首页：滚一段看介绍与 16 型卡片
            page.wait_for_timeout(700)
            smooth_scroll(page, 1200, steps=14)
            page.wait_for_timeout(500)

            # ② 登录
            login(page)
            page.wait_for_timeout(500)

            # ③ 答题：点几题，展示选中态与进度变化
            page.goto(f'{BASE}/test/', wait_until='networkidle')
            page.wait_for_timeout(900)
            answer_visible(page, count=4)
            page.wait_for_timeout(500)

            # ④ 结果页。不走表单提交：93 题里只有第 1 页是现场点的，
            # 提交会因为"还有未答题"被拦下。直接算好结果再跳过去。
            code = prep('result')
            print(f'  {code}')
            page.goto(f'{BASE}/result/', wait_until='networkidle')
            # 护栏：掉登录态时 /result/ 会重定向回登录页，成片最后一段变成
            # 登录表单而不报错。断言类型码真的渲染出来了。
            page.wait_for_selector('.result-type-code', timeout=10_000)
            shown = page.inner_text('.result-type-code').strip()
            if len(shown) != 4:
                raise RuntimeError(f'结果页没渲染出类型码，实际是 {shown!r}')
            print(f'  结果页显示 {shown}')
            page.wait_for_timeout(1300)
            smooth_scroll(page, 900, steps=16)
            page.wait_for_timeout(1000)
        finally:
            cast.stop()
            measured = cast.fps
            ctx.close()
            browser.close()

    print(f'  screencast 收到 {len(cast.paths)} 帧（{measured:.0f} fps）')
    return cast.paths, measured


def resample(frames, target_fps, source_fps):
    """screencast 是变帧率（只在画面有变化时发帧），按时间均匀抽到目标帧率。

    每 N 帧硬取一帧会把"页面静止"和"动画密集"压成同样时长，节奏会失真。
    """
    if not frames or target_fps >= source_fps:
        return frames
    step = source_fps / target_fps
    picked, i = [], 0.0
    while i < len(frames):
        picked.append(frames[int(i)])
        i += step
    return picked


def drop_unsettled_head(frames, lookahead=4, tol=0.012):
    """裁掉开头没稳定下来的帧。

    判据是"稳定"而不是"够亮/颜色够多"：找第一个和其后 lookahead 帧几乎无差异
    的帧。入场动画在动就不稳定，长好了才稳定。GitHub 拿首帧当封面，
    这一帧错了等于 README 顶部没图。
    """
    from PIL import Image, ImageChops

    def thumb(path):
        return Image.open(path).convert('RGB').resize((96, 60), Image.BILINEAR)

    for i in range(len(frames) - lookahead):
        a, b = thumb(frames[i]), thumb(frames[i + lookahead])
        diff = ImageChops.difference(a, b)
        score = sum(sum(px) for px in diff.getdata()) / (96 * 60 * 3 * 255)
        if score < tol:
            return frames[i:], i
    return frames, 0


def build_gif(frames, out, colors, delay, diff_thresh):
    """用一张共享调色板量化所有帧。

    每帧各自量化时，同一块没变的区域会落到不同的调色板索引上，帧间就压不动了。
    disposal 必须是 1：用 2 会让每帧先恢复背景，同样毁掉帧间压缩。
    """
    from PIL import Image, ImageChops

    def load(path):
        return Image.open(path).convert('RGB')

    # 主调色板从整段均匀取样，不能只用首帧 —— 后面才出现的颜色（结果页的
    # 维度条渐变、类型色块）没进调色板就会偏色。
    probe = [load(f) for f in frames[::max(1, len(frames) // 14)]]
    strip = Image.new('RGB', (probe[0].width, probe[0].height * len(probe)))
    for i, im in enumerate(probe):
        strip.paste(im, (0, i * probe[0].height))
    master = strip.quantize(colors=colors, method=Image.MEDIANCUT)

    imgs, delays, prev = [], [], None
    for f in frames:
        im = load(f)
        if prev is not None:
            bbox = ImageChops.difference(im, prev).getbbox()
            area = 0 if bbox is None else (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
            if area < diff_thresh:      # 画面基本没动：并进上一帧、延长停留
                delays[-1] += delay
                continue
        imgs.append(im.quantize(palette=master, dither=Image.NONE))
        delays.append(delay)
        prev = im

    imgs[0].save(out, save_all=True, append_images=imgs[1:], duration=delays,
                 loop=0, optimize=True, disposal=1)
    return len(imgs), sum(delays) / 1000


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--fps', type=int, default=10)
    # 页面有大面积紫蓝渐变（hero、维度条），正是量化的最坏情况。
    # 128 色会压出色阶断层，看着像图片坏了 —— 上一版就是 128 色。
    ap.add_argument('--colors', type=int, default=220)
    ap.add_argument('--diff-thresh', type=int, default=800)
    ap.add_argument('--max-seconds', type=int, default=60,
                    help='成片时长上限，超了报错而不是产出废 GIF')
    ap.add_argument('--from-frames', help='跳过录制，用现成帧目录重新合成')
    ap.add_argument('--source-fps', type=float, default=60,
                    help='配合 --from-frames：原始帧的采集帧率')
    ap.add_argument('--keep-frames', action='store_true',
                    help='保留原始 PNG 帧，便于反复调参不重录')
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.from_frames:
        frame_dir = Path(args.from_frames)
        frames = sorted(frame_dir.glob('*.png'))
        cleanup, source_fps = False, args.source_fps
    else:
        frame_dir = Path(tempfile.mkdtemp(prefix='mbti-frames-'))
        cleanup = not args.keep_frames
        frames, source_fps = record(frame_dir)

    gif = OUT_DIR / 'demo.gif'
    try:
        if not frames:
            print('!! 一帧都没收到，screencast 没工作')
            return 1
        frames, dropped = drop_unsettled_head(frames)
        if dropped:
            print(f'裁掉开头 {dropped} 帧未稳定画面')

        kept_src = len(frames)
        frames = resample(frames, args.fps, max(args.fps, source_fps))
        print(f'{kept_src} 帧 -> 抽为 {len(frames)} 帧，合成 GIF…')

        # 护栏：某个等待卡住时会安静产出超长废片，宁可报错。
        if len(frames) > args.max_seconds * args.fps:
            print(f'!! 成片会有 {len(frames) / args.fps:.0f}s，超过 '
                  f'{args.max_seconds}s 上限，说明某处在干等，别合成了')
            return 1

        kept, secs = build_gif(frames, gif, args.colors,
                               round(1000 / args.fps), args.diff_thresh)
    finally:
        if cleanup:
            shutil.rmtree(frame_dir, ignore_errors=True)
        else:
            print(f'原始帧保留在 {frame_dir}')

    size_mb = gif.stat().st_size / 1024 / 1024
    print(f'\n{gif.relative_to(ROOT)}  {kept} 帧 / {secs:.1f}s / {size_mb:.2f} MB')
    if size_mb > 8:
        print('   偏大，建议降 --fps 或缩短流程')
    return 0


if __name__ == '__main__':
    sys.exit(main())
