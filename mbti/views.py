from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.conf import settings
from django.http import JsonResponse
from .models import Question, Response, Result, Questionnaire, TypeProfile
import json



def home_view(request):
    return render(request, 'mbti/home.html')


@login_required
def test_view(request):
    qnn = Questionnaire.objects.filter(is_active=True).first()
    questions = Question.objects.filter(active=True, questionnaire=qnn).order_by('order', 'id') if qnn else Question.objects.filter(active=True).order_by('order', 'id')
    
    # 检查是否有题目
    if not questions.exists():
        messages.error(request, '暂可用测试题目，请联系管理员。')
        return redirect('mbti:home')
    
    # 分页处理
    from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
    page_number = request.GET.get('page', 1)
    paginator = Paginator(questions, 10)  # 每页10题
    
    try:
        page_obj = paginator.page(page_number)
    except PageNotAnInteger:
        # 如果页码不是整数，显示第一页
        page_obj = paginator.page(1)
    except EmptyPage:
        # 如果页码超出范围，显示最后一页
        page_obj = paginator.page(paginator.num_pages)
    
    # 获取已保存的答案（会话中以 q_<id> 形式存储，这里转换为 {question_id: value}）
    saved_answers = {}
    if hasattr(request, 'session'):
        raw_answers = request.session.get('test_answers', {})
        normalized = {}
        for k, v in raw_answers.items():
            try:
                if isinstance(k, str) and k.startswith('q_'):
                    qid = int(k.split('_')[1])
                    normalized[qid] = str(v)
            except Exception:
                continue
        saved_answers = normalized
    
    return render(request, 'mbti/test.html', {
        "page_obj": page_obj,
        "saved_answers": saved_answers,
        "total_questions": questions.count(),
        "current_page": page_obj.number,
        "total_pages": paginator.num_pages  # 明确传递总页数
    })


@login_required
def save_progress_view(request):
    """保存测试进度的AJAX视图"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            answers = data.get('answers', {})
            
            # 保存到session
            if not request.session.get('test_answers'):
                request.session['test_answers'] = {}
            request.session['test_answers'].update(answers)
            request.session.modified = True
            
            return JsonResponse({'status': 'success'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)})
    
    return JsonResponse({'status': 'error', 'message': 'Invalid method'})


@login_required
def submit_view(request):
    if request.method != 'POST':
        return redirect('mbti:test')

    # 合并session中的答案和当前提交的答案
    all_answers = {}
    if hasattr(request, 'session'):
        all_answers.update(request.session.get('test_answers', {}))
    
    # 添加当前页面的答案
    for key, val in request.POST.items():
        if key.startswith('q_'):
            all_answers[key] = val

    qnn = Questionnaire.objects.filter(is_active=True).first()
    answers = {}
    for key, val in all_answers.items():
        if key.startswith('q_'):
            try:
                qid = int(key.split('_')[1])
                answers[qid] = int(val)
            except (ValueError, IndexError):
                pass

    # 检查是否所有题目都已回答
    questions = Question.objects.filter(active=True, questionnaire=qnn).order_by('order', 'id') if qnn else Question.objects.filter(active=True).order_by('order', 'id')
    required_questions = set(questions.values_list('id', flat=True))
    answered_questions = set(answers.keys())
    
    if not required_questions.issubset(answered_questions):
        missing_count = len(required_questions - answered_questions)
        messages.error(request, f'还有 {missing_count} 道题未完成，请完成所有题目后再提交。')
        return redirect('mbti:test')

    # 清除session中的答案
    if hasattr(request, 'session') and 'test_answers' in request.session:
        del request.session['test_answers']

    for qid, choice in answers.items():
        Response.objects.update_or_create(
            user=request.user,
            question_id=qid,
            defaults={"choice": choice, "questionnaire": qnn},
        )

    # 计算得分
    dims = {"IE": 0.0, "SN": 0.0, "TF": 0.0, "JP": 0.0}
    counts = {"IE": 0, "SN": 0, "TF": 0, "JP": 0}
    for resp in Response.objects.filter(user=request.user).select_related('question'):
        dim = resp.question.dimension
        if dim in dims:
            # 标准化计分：Likert(1..5)→[-2..+2]；确保各维度正分恒指向“第二字母”
            raw = resp.choice - 3  # -2..+2
            pole_pair = {
                "IE": ("I", "E"),
                "SN": ("S", "N"),
                "TF": ("T", "F"),
                "JP": ("J", "P"),
            }[dim]
            # 若题目倾向的是第二极性（如E、N、F、P），则正向；否则反向
            direction = 1 if resp.question.keyed_pole == pole_pair[1] else -1
            score = raw * direction * max(1, resp.question.weight)
            dims[dim] += score
            counts[dim] += 1

    # 生成类型码
    type_map = {
        "IE": ("I", "E"),
        "SN": ("S", "N"),
        "TF": ("T", "F"),
        "JP": ("J", "P"),
    }
    # 映射逻辑修正：dims中分数的正负与模板一致：
    # 约定 v>0 代表维度字符串的第二极性（如 IE 中的 E），v<0 代表第一极性（如 I）。
    # 过去用 v>=0 归到第一极性会造成边界与符号反转，引发类型与维度不一致。
    code = "".join([type_map[k][1] if v > 0 else type_map[k][0] for k, v in dims.items()])
    # 置信度：按每维度平均绝对分值归一化（0..1），分值越高置信度越高
    confidence = {}
    for k, v in dims.items():
        n = max(counts[k], 1)
        # 每题最大绝对分值=2*weight，这里按weight最小值1近似；平均绝对值/2归一到[0,1]
        confidence[k] = min(1.0, max(0.0, (abs(v) / n) / 2))

    qnn = Questionnaire.objects.filter(is_active=True).first()
    result, _ = Result.objects.update_or_create(
        user=request.user,
        defaults={"type_code": code, "score_detail": dims, "confidence": confidence, "questionnaire": qnn},
    )

    messages.success(request, '提交成功，以下是你的测试结果')
    return redirect('mbti:result')


@login_required
def result_view(request):
    result = Result.objects.filter(user=request.user).first()
    score_items = list(result.score_detail.items()) if result else []
    confidence = result.confidence if result else {}
    detail_items = [(k, v, confidence.get(k)) for (k, v) in score_items]
    profile = TypeProfile.objects.filter(code=result.type_code).first() if result else None
    return render(request, 'mbti/result.html', {"result": result, "detail_items": detail_items, "profile": profile})


@login_required
def result_pdf_view(request):
    result = Result.objects.filter(user=request.user).first()
    if not result:
        return redirect('mbti:test')

    # 延迟导入报告库，给出友好降级
    try:
        from reportlab.lib.pagesizes import A4, letter
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        from reportlab.lib.units import inch
    except Exception:
        messages.error(request, 'PDF导出模块未安装，请稍后重试或联系管理员安装 reportlab')
        return redirect('mbti:result')

    # 注册中文字体，避免乱码（跨平台）
    base_font = 'Helvetica'
    try:
        import os, sys
        # 常见平台字体路径（包含 Windows、Linux(Ubuntu) 与 macOS）
        font_paths = [
            # Windows
            r'C:\Windows\Fonts\msyh.ttf',  # 微软雅黑 (TTF)
            r'C:\Windows\Fonts\msyh.ttc',  # 微软雅黑 (TTC)
            r'C:\Windows\Fonts\simhei.ttf',  # 黑体
            r'C:\Windows\Fonts\simsun.ttc',  # 宋体（可能不被TTFont识别）
            r'C:\Windows\Fonts\simsun.ttf',  # 宋体 (TTF)
            r'C:\Windows\Fonts\NSimSun.ttf',  # 新宋体
            r'C:\Windows\Fonts\SIMKAI.TTF',  # 楷体
        ]

        # Linux 常见中文字体（优先使用 Noto/思源系列，ReportLab 对 OTF/TTF支持更稳定）
        linux_candidates = [
            '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
            '/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf',
            '/usr/share/fonts/noto-cjk/NotoSansCJKsc-Regular.otf',
            '/usr/share/fonts/noto/NotoSansCJKsc-Regular.otf',
            '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',
            '/usr/share/fonts/truetype/wqy/wqy-microhei.ttc',
            '/usr/share/fonts/truetype/arphic/ukai.ttf',
            '/usr/share/fonts/truetype/arphic/uming.ttf',
        ]

        # macOS 常见中文字体
        mac_candidates = [
            '/System/Library/Fonts/PingFang.ttc',
            '/System/Library/Fonts/STSong.ttf',
            '/Library/Fonts/Songti.ttc',
            '/Library/Fonts/Heiti.ttc',
        ]

        if sys.platform.startswith('linux'):
            font_paths.extend(linux_candidates)
        elif sys.platform == 'darwin':
            font_paths.extend(mac_candidates)

        # 项目内置字体（如存在）：static/fonts/NotoSansCJKsc-Regular.otf
        BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        project_font = os.path.join(BASE_DIR, 'static', 'fonts', 'NotoSansCJKsc-Regular.otf')
        font_paths.append(project_font)

        for font_path in font_paths:
            try:
                if os.path.exists(font_path):
                    pdfmetrics.registerFont(TTFont('CN', font_path))
                    base_font = 'CN'
                    break
            except Exception:
                # 某些 .ttc 字体包不被 TTFont 支持，继续尝试下一个
                continue
        # 若仍未找到可用 TTF/TTC，尝试使用内置的 CJK 字体（不需外部文件）
        if base_font == 'Helvetica':
            try:
                pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
                base_font = 'STSong-Light'
            except Exception:
                pass
    except Exception:
        # 字体注册失败时退回默认英文字体（中文可能出现方块）
        pass

    # 样式
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontName=base_font,
        fontSize=20,
        spaceAfter=30,
        alignment=1,  # 居中
        textColor=colors.darkblue
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontName=base_font,
        fontSize=14,
        spaceAfter=12,
        spaceBefore=20,
        textColor=colors.darkblue,
        borderWidth=1,
        borderColor=colors.lightgrey,
        borderPadding=5,
        backColor=colors.lightgrey
    )
    
    normal_style = ParagraphStyle(
        'CustomNormal',
        parent=styles['Normal'],
        fontName=base_font,
        fontSize=10,
        spaceAfter=8,
        leftIndent=20,
        rightIndent=20
    )
    
    info_style = ParagraphStyle(
        'InfoStyle',
        parent=styles['Normal'],
        fontName=base_font,
        fontSize=10,
        spaceAfter=6,
        leftIndent=10
    )

    # 类型档案
    profile = TypeProfile.objects.filter(code=result.type_code).first()
    strengths = getattr(profile, 'strengths', '') or '—'
    growth = getattr(profile, 'growth', '') or '—'
    description = getattr(profile, 'description', '') or '—'

    # 构建文档
    from io import BytesIO
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=50, bottomMargin=50, title='MBTI人格测试报告')
    story = []
    
    # 添加标题
    story.append(Paragraph('MBTI人格测试报告', title_style))
    story.append(Spacer(1, 30))
    
    # 基本信息表格
    story.append(Paragraph('基本信息', heading_style))
    basic_data = [
        ['用户名', request.user.username],
        ['测试时间', result.created_at.strftime('%Y年%m月%d日 %H:%M') if hasattr(result, 'created_at') else '—'],
        ['人格类型', f"{result.type_code} - {getattr(profile, 'name', '未知类型') if profile else '未知类型'}"],
        ['测试题目数', Response.objects.filter(user=request.user).count()]
    ]
    
    basic_table = Table(basic_data, colWidths=[2*inch, 4*inch])
    basic_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, -1), base_font),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ('BACKGROUND', (1, 0), (1, -1), colors.white),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    story.append(basic_table)
    story.append(Spacer(1, 20))
    
    # 类型描述
    story.append(Paragraph('性格概述', heading_style))
    story.append(Paragraph(description, normal_style))
    story.append(Spacer(1, 20))
    
    # 维度分析表格
    story.append(Paragraph('维度分析', heading_style))
    
    dimension_data = [['维度', '分数', '置信度', '倾向']] + [
        [
            k, 
            f"{v:+.2f}", 
            f"{result.confidence.get(k, 0):.2f}",
            {'IE': ('内向', '外向'), 'SN': ('感觉', '直觉'), 'TF': ('思考', '情感'), 'JP': ('判断', '知觉')}[k][1 if v > 0 else 0]
        ] for k, v in result.score_detail.items()
    ]
    
    dimension_table = Table(dimension_data, colWidths=[1.5*inch, 1*inch, 1*inch, 1.5*inch])
    dimension_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, -1), base_font),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    story.append(dimension_table)
    story.append(Spacer(1, 20))
    
    # 多维度深度分析
    story.append(Paragraph('多维度深度分析', heading_style))
    
    analysis_sections = [
        ('性格特点', getattr(profile, 'personality_traits', '') if profile else ''),
        ('工作风格', getattr(profile, 'work_style', '') if profile else ''),
        ('人际关系', getattr(profile, 'interpersonal_relations', '') if profile else ''),
        ('情感表达', getattr(profile, 'emotional_expression', '') if profile else ''),
        ('决策方式', getattr(profile, 'decision_making', '') if profile else ''),
        ('压力管理', getattr(profile, 'stress_management', '') if profile else ''),
        ('学习方式', getattr(profile, 'learning_style', '') if profile else ''),
        ('职业建议', getattr(profile, 'career_suggestions', '') if profile else ''),
        ('生活哲学', getattr(profile, 'life_philosophy', '') if profile else ''),
        ('沟通风格', getattr(profile, 'communication_style', '') if profile else '')
    ]
    
    for section_title, content in analysis_sections:
        if content:  # 只显示有内容的部分
            story.append(Paragraph(f"• {section_title}", ParagraphStyle(
                'SectionTitle',
                parent=normal_style,
                fontSize=12,
                textColor=colors.darkblue,
                spaceAfter=6,
                leftIndent=10,
                fontName=base_font
            )))
            story.append(Paragraph(content, normal_style))
            story.append(Spacer(1, 10))
    
    # 详细维度分析
    story.append(Paragraph('维度详细分析', heading_style))
    
    # 为每个维度提供详细解释
    dimension_explanations = {
        'IE': {
            'name': '外向性 vs 内向性',
            'description': '这个维度反映了你获取能量的方式和注意力的方向。',
            'I': '内向型：从内部世界获取能量，喜欢独处思考，更关注内心世界。',
            'E': '外向型：从外部世界获取能量，喜欢与人交往，思考时倾向于外化表达。'
        },
        'SN': {
            'name': '感觉 vs 直觉',
            'description': '这个维度反映了你收集和处理信息的偏好方式。',
            'S': '感觉型：关注具体事实和细节，相信经验和实际观察，注重现实。',
            'N': '直觉型：关注可能性和模式，相信灵感和想象，注重未来潜力。'
        },
        'TF': {
            'name': '思考 vs 情感',
            'description': '这个维度反映了你做决策时的主要考虑因素。',
            'T': '思考型：基于逻辑分析做决策，重视客观标准和公平原则。',
            'F': '情感型：基于价值观和人际关系做决策，重视和谐与个人价值。'
        },
        'JP': {
            'name': '判断 vs 知觉',
            'description': '这个维度反映了你对外部世界的态度和生活方式偏好。',
            'J': '判断型：喜欢有计划和结构的生活，倾向于做决定和完成任务。',
            'P': '知觉型：喜欢灵活和开放的生活，倾向于保持选择余地和适应变化。'
        }
    }
    
    for dim_code, score in result.score_detail.items():
        if dim_code in dimension_explanations:
            dim_info = dimension_explanations[dim_code]
            confidence = result.confidence.get(dim_code, 0)
            
            # 维度标题
            story.append(Paragraph(f"{dim_info['name']} ({dim_code})", ParagraphStyle(
                'DimensionTitle',
                parent=normal_style,
                fontSize=13,
                textColor=colors.darkred,
                spaceAfter=8,
                spaceBefore=15,
                fontName=base_font,
                bold=True
            )))
            
            # 维度描述
            story.append(Paragraph(dim_info['description'], normal_style))
            
            # 分数与倾向：按分数符号选择维度对应字母的解释
            type_map = {
                'IE': ('I', 'E'),
                'SN': ('S', 'N'),
                'TF': ('T', 'F'),
                'JP': ('J', 'P'),
            }
            chosen_letter = type_map[dim_code][1] if score > 0 else type_map[dim_code][0]
            tendency = dim_info.get(chosen_letter, '')
            score_text = f"您的分数：{score:+.2f}，置信度：{confidence:.2f}"
            
            story.append(Paragraph(f"<b>{score_text}</b>", ParagraphStyle(
                'ScoreText',
                parent=normal_style,
                fontSize=11,
                textColor=colors.darkgreen,
                spaceAfter=6,
                leftIndent=20,
                fontName=base_font
            )))
            
            story.append(Paragraph(tendency, ParagraphStyle(
                'TendencyText',
                parent=normal_style,
                fontSize=10,
                leftIndent=20,
                rightIndent=20,
                spaceAfter=10,
                fontName=base_font,
                backColor=colors.lightgrey,
                borderWidth=1,
                borderColor=colors.grey,
                borderPadding=8
            )))
    
    # 综合分析
    story.append(Paragraph('综合人格分析', heading_style))
    
    # 计算整体倾向强度
    total_strength = sum(abs(score) for score in result.score_detail.values()) / len(result.score_detail)
    avg_confidence = sum(result.confidence.values()) / len(result.confidence) if result.confidence else 0
    
    overall_analysis = f"""
    根据您的测试结果，您的人格类型为 {result.type_code}。
    
    整体特征强度：{total_strength:.2f}（范围0-4，数值越高表示特征越明显）
    平均置信度：{avg_confidence:.2f}（范围0-1，数值越高表示结果越可靠）
    
    这意味着您在各个维度上的倾向性{'较为明显' if total_strength > 2 else '相对温和'}，
    测试结果的可靠性{'较高' if avg_confidence > 0.7 else '中等' if avg_confidence > 0.5 else '需要进一步验证'}。
    """
    
    story.append(Paragraph(overall_analysis, normal_style))
    story.append(Spacer(1, 15))
    
    # 发展建议增强版
    story.append(Paragraph('个人发展建议', heading_style))
    
    # 基于分数提供个性化建议
    development_suggestions = []
    
    for dim_code, score in result.score_detail.items():
        confidence = result.confidence.get(dim_code, 0)
        if confidence < 0.6:  # 低置信度的维度
            if dim_code == 'IE':
                development_suggestions.append("在内外向维度上，您可能处于平衡状态。建议在不同情境下尝试不同的行为模式，找到最适合的能量获取方式。")
            elif dim_code == 'SN':
                development_suggestions.append("在感觉-直觉维度上，您展现出灵活性。建议培养既关注细节又把握大局的能力。")
            elif dim_code == 'TF':
                development_suggestions.append("在思考-情感维度上，您能够平衡理性和感性。建议在决策时综合考虑逻辑分析和人际影响。")
            elif dim_code == 'JP':
                development_suggestions.append("在判断-知觉维度上，您具有适应性。建议根据情况需要，灵活运用计划性和开放性。")
    
    if development_suggestions:
        story.append(Paragraph("基于您的测试结果，以下是个性化的发展建议：", normal_style))
        for i, suggestion in enumerate(development_suggestions, 1):
            story.append(Paragraph(f"{i}. {suggestion}", ParagraphStyle(
                'SuggestionText',
                parent=normal_style,
                leftIndent=30,
                rightIndent=20,
                spaceAfter=8,
                fontName=base_font
            )))
    
    # 原有的发展建议
    if growth:
        story.append(Paragraph("通用发展建议：", normal_style))
        story.append(Paragraph(growth, normal_style))
    
    story.append(Spacer(1, 20))

    # 页脚信息
    story.append(Spacer(1, 30))
    footer_style = ParagraphStyle(
        'Footer',
        parent=styles['Normal'],
        fontName=base_font,
        fontSize=8,
        alignment=1,
        textColor=colors.grey
    )
    story.append(Paragraph('本报告由MBTI人格测试系统生成', footer_style))
    story.append(Paragraph(f"生成时间：{result.created_at.strftime('%Y年%m月%d日 %H:%M:%S') if hasattr(result, 'created_at') else '—'}", footer_style))

    doc.build(story)
    buffer.seek(0)

    from django.http import HttpResponse
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="MBTI测试报告_{request.user.username}_{result.created_at.strftime("%Y%m%d") if hasattr(result, "created_at") else "report"}.pdf"'
    return response