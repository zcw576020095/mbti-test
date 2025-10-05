import os
import sys
import csv

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mbti_site.settings')


def load_csv_questions(csv_path):
    items = []
    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, start=1):
            items.append({
                'text': (row.get('text') or '').strip(),
                'dimension': (row.get('dimension') or '').strip().upper(),
                'keyed_pole': (row.get('keyed_pole') or '').strip().upper(),
                'weight': int((row.get('weight') or '1').strip() or 1),
                'order': int((row.get('order') or str(i)).strip() or i),
            })
    return items


def seed_questions_hardcoded():
    # 如需“写死题目”，可将 CSV 内容复制为列表返回；现暂留占位以避免误用。
    return []


def main():
    try:
        import django
        django.setup()
    except Exception as e:
        print(f"[ERROR] 初始化 Django 失败：{e}")
        sys.exit(1)

    from mbti.models import Questionnaire, Question

    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(BASE_DIR, 'data', 'questions_open_mbti_cn.csv')

    questions = []
    try:
        if os.path.exists(csv_path):
            questions = load_csv_questions(csv_path)
            print(f"[INFO] 从 CSV 载入题库：{csv_path}（{len(questions)} 条）")
        else:
            questions = seed_questions_hardcoded()
            print(f"[WARN] 未找到 CSV，使用写死题库（{len(questions)} 条）")
    except Exception as e:
        print(f"[ERROR] 读取题库失败：{e}")
        sys.exit(2)

    # 创建/更新问卷
    qkey = 'mbti_open_v1'
    qname = 'MBTI测试（开放版）'
    qnn, _ = Questionnaire.objects.get_or_create(key=qkey, defaults={'name': qname, 'description': '开放版平衡题库'})
    qnn.name = qname
    qnn.save()

    created, updated = 0, 0
    valid_dims = {'IE': ('I', 'E'), 'SN': ('S', 'N'), 'TF': ('T', 'F'), 'JP': ('J', 'P')}

    for item in questions:
        text = item.get('text', '').strip()
        dim = item.get('dimension', '').upper()
        pole = item.get('keyed_pole', '').upper()
        weight = int(item.get('weight', 1) or 1)
        order = int(item.get('order', 0) or 0)

        if not text or dim not in valid_dims or pole not in valid_dims[dim]:
            continue

        obj, created_flag = Question.objects.update_or_create(
            text=text,
            questionnaire=qnn,
            defaults={
                'dimension': dim,
                'keyed_pole': pole,
                'weight': weight,
                'order': order,
                'active': True,
            }
        )
        if created_flag:
            created += 1
        else:
            updated += 1

    # 激活该问卷
    Questionnaire.objects.exclude(id=qnn.id).update(is_active=False)
    qnn.is_active = True
    qnn.save()

    print(f"[DONE] 导入完成：新建 {created} 条，更新 {updated} 条；激活问卷：{qnn.key}")


if __name__ == '__main__':
    main()