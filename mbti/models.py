from django.db import models
from django.contrib.auth.models import User


class Questionnaire(models.Model):
    key = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Question(models.Model):
    text = models.CharField(max_length=255)
    dimension = models.CharField(max_length=2)  # IE, SN, TF, JP
    # 题目方向：在对应维度上更偏向哪个极性（例如IE中的I或E）
    keyed_pole = models.CharField(max_length=1, default="I")
    weight = models.IntegerField(default=1)
    order = models.IntegerField(default=0)
    active = models.BooleanField(default=True)
    questionnaire = models.ForeignKey(
        Questionnaire, on_delete=models.CASCADE, related_name="questions", null=True, blank=True
    )

    def __str__(self):
        return self.text


class Response(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    choice = models.IntegerField()  # 1..5 Likert
    questionnaire = models.ForeignKey(Questionnaire, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "question")


class Result(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    type_code = models.CharField(max_length=4)  # e.g., INTP
    score_detail = models.JSONField(default=dict)
    confidence = models.JSONField(default=dict)  # 每个维度的置信度(0..1)
    questionnaire = models.ForeignKey(Questionnaire, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class TypeProfile(models.Model):
    code = models.CharField(max_length=4, unique=True)  # 16类类型码
    name = models.CharField(max_length=100, blank=True)
    description = models.TextField(blank=True)
    strengths = models.TextField(blank=True)
    growth = models.TextField(blank=True)
    
    # 新增多维度分析字段
    personality_traits = models.TextField(blank=True, verbose_name="性格特点")
    work_style = models.TextField(blank=True, verbose_name="工作风格")
    interpersonal_relations = models.TextField(blank=True, verbose_name="人际关系")
    emotional_expression = models.TextField(blank=True, verbose_name="情感表达")
    decision_making = models.TextField(blank=True, verbose_name="决策方式")
    stress_management = models.TextField(blank=True, verbose_name="压力管理")
    learning_style = models.TextField(blank=True, verbose_name="学习方式")
    career_suggestions = models.TextField(blank=True, verbose_name="职业建议")
    life_philosophy = models.TextField(blank=True, verbose_name="生活哲学")
    communication_style = models.TextField(blank=True, verbose_name="沟通风格")

    def __str__(self):
        return self.code