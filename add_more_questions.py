#!/usr/bin/env python
import os
import django

# 设置Django环境
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mbti_site.settings')
django.setup()

from mbti.models import Question

# 新增的MBTI测试题目
new_questions = [
    {
        'text': '我喜欢在社交聚会中主动与多人交谈，成为焦点',
        'dimension': 'EI',
        'keyed_pole': 'E'
    },
    {
        'text': '面对新挑战时，我倾向于立即行动，边做边学',
        'dimension': 'SN',
        'keyed_pole': 'S'
    },
    {
        'text': '在做重要决定时，我更依赖逻辑分析和客观事实',
        'dimension': 'TF',
        'keyed_pole': 'T'
    },
    {
        'text': '我喜欢有明确的计划和时间表',
        'dimension': 'JP',
        'keyed_pole': 'J'
    },
    {
        'text': '学习新知识时，我更喜欢从具体例子开始理解',
        'dimension': 'SN',
        'keyed_pole': 'S'
    },
    {
        'text': '当朋友向我倾诉烦恼时，我倾向于提供实用的解决方案',
        'dimension': 'TF',
        'keyed_pole': 'T'
    },
    {
        'text': '在工作环境中，我喜欢与团队成员频繁互动',
        'dimension': 'EI',
        'keyed_pole': 'E'
    },
    {
        'text': '我习惯提前完成任务，避免最后匆忙',
        'dimension': 'JP',
        'keyed_pole': 'J'
    },
    {
        'text': '阅读时，我更关注作者想要表达的深层含义',
        'dimension': 'SN',
        'keyed_pole': 'N'
    },
    {
        'text': '在冲突中，我倾向于直接指出问题所在',
        'dimension': 'TF',
        'keyed_pole': 'T'
    },
    {
        'text': '休息时间，我更愿意和朋友一起活动',
        'dimension': 'EI',
        'keyed_pole': 'E'
    },
    {
        'text': '对于未来，我更关注可能性和潜在机会',
        'dimension': 'SN',
        'keyed_pole': 'N'
    },
    {
        'text': '评价他人时，我更看重能力和成就',
        'dimension': 'TF',
        'keyed_pole': 'T'
    },
    {
        'text': '我欢迎变化，喜欢寻求新体验',
        'dimension': 'JP',
        'keyed_pole': 'P'
    },
    {
        'text': '在团队项目中，我更愿意负责协调和沟通',
        'dimension': 'EI',
        'keyed_pole': 'E'
    },
    {
        'text': '处理信息时，我倾向于关注细节和具体数据',
        'dimension': 'SN',
        'keyed_pole': 'S'
    },
    {
        'text': '批评他人时，我会直接指出问题',
        'dimension': 'TF',
        'keyed_pole': 'T'
    },
    {
        'text': '我认为规则和制度应该严格遵守',
        'dimension': 'JP',
        'keyed_pole': 'J'
    },
    {
        'text': '聚会结束后，我通常感到精力充沛，想继续社交',
        'dimension': 'EI',
        'keyed_pole': 'E'
    },
    {
        'text': '解决问题时，我更依赖过往经验和已知方法',
        'dimension': 'SN',
        'keyed_pole': 'S'
    }
]

def add_questions():
    print("开始添加新题目...")
    
    for i, q_data in enumerate(new_questions, 1):
        question, created = Question.objects.get_or_create(
            text=q_data['text'],
            defaults={
                'dimension': q_data['dimension'],
                'keyed_pole': q_data['keyed_pole'],
                'weight': 1,
                'order': i + 100,  # 避免与现有题目冲突
                'active': True
            }
        )
        
        if created:
            print(f"添加题目 {i}: {q_data['text'][:30]}...")
        else:
            print(f"题目已存在: {q_data['text'][:30]}...")
    
    total_questions = Question.objects.count()
    print(f"\n题目添加完成！当前总题目数: {total_questions}")

if __name__ == '__main__':
    add_questions()