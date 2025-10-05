from django.contrib import admin
from .models import Questionnaire, Question, Response, Result, TypeProfile


@admin.register(Questionnaire)
class QuestionnaireAdmin(admin.ModelAdmin):
    list_display = ("key", "name", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("key", "name")


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("text", "dimension", "keyed_pole", "weight", "order", "active", "questionnaire")
    list_filter = ("dimension", "active")
    search_fields = ("text",)
    list_editable = ("keyed_pole", "weight", "order", "active")


@admin.register(Response)
class ResponseAdmin(admin.ModelAdmin):
    list_display = ("user", "question", "choice", "questionnaire", "created_at")
    list_filter = ("questionnaire", "question__dimension")
    search_fields = ("user__username", "question__text")


@admin.register(Result)
class ResultAdmin(admin.ModelAdmin):
    list_display = ("user", "type_code", "questionnaire", "created_at")
    list_filter = ("questionnaire",)
    search_fields = ("user__username", "type_code")


@admin.register(TypeProfile)
class TypeProfileAdmin(admin.ModelAdmin):
    list_display = ("code", "name")
    search_fields = ("code", "name")