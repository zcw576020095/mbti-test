from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.contrib.auth.hashers import make_password

from .forms import RegisterForm, LoginForm


def register_view(request):
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = User(
                username=form.cleaned_data['username'],
                email=form.cleaned_data['email'],
                password=make_password(form.cleaned_data['password']),
            )
            user.save()
            messages.success(request, '注册成功，请登录')
            return redirect('users:login')
    else:
        form = RegisterForm()
    return render(request, 'users/register.html', {'form': form})


def login_view(request):
    if request.method == 'POST':
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            user = authenticate(
                request,
                username=form.cleaned_data['username'],
                password=form.cleaned_data['password']
            )
            if user is not None:
                login(request, user)
                messages.success(request, '登录成功')
                return redirect('mbti:home')
            else:
                messages.error(request, '用户名或密码错误')
        else:
            messages.error(request, '请输入有效的用户名和密码')
    else:
        form = LoginForm()
    return render(request, 'users/login.html', {'form': form})


def logout_view(request):
    logout(request)
    messages.info(request, '已退出登录')
    return redirect('users:login')


@login_required
def password_change_view(request):
    if request.method == 'POST':
        pwd1 = request.POST.get('password')
        pwd2 = request.POST.get('confirm_password')
        if not pwd1 or pwd1 != pwd2:
            messages.error(request, '两次输入的密码不一致')
        else:
            request.user.set_password(pwd1)
            request.user.save()
            messages.success(request, '密码修改成功，请重新登录')
            return redirect('users:login')
    return render(request, 'users/password_change.html')