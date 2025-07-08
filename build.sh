#!/usr/bin/env bash

# Установка зависимостей
pip install -r requirements.txt

# Применение миграций
python manage.py migrate

# Сбор статики
python manage.py collectstatic --noinput
