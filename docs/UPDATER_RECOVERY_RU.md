# Восстановление обновления YadroKreator и отдельный журнал установщика

## Почему у старой панели нет шкалы обновления

Если установлена версия `18b72496492d`, а установка нового `main` падает,
страница остаётся старой: графический индикатор ещё **не установлен**.
Вкладка «Сборки» выводит *только* задания компиляции WIFICAM/Thingino, она
**не предназначена для диагностики обновления Flask/Waitress**.

Старый updater обрезал **начало** текста тестов до 350 символов: `test_... ok`
в сообщении об ошибке не означает, что весь набор тестов прошёл. Полную
причину нужно смотреть через `journalctl --user` для unit обновления.

Новая панель в разделе **Система → Обновления** содержит отдельную консоль
только для Git, Python-пакетов, unit-тестов, перезапуска и итогового статуса.
События остаются в `/1tbdisk/PegineLab/factory-state/update-logs/<operation>.log`
с доступом `0600`. Ошибка показывает конкретный этап и **конец** сообщения
о сбое, включая окончание traceback. Никаких логов прошивки там нет.

## Что выполнить на сервере, если прежнее обновление завершилось ошибкой

Проверить, что нет активной операции и активных сборок, а Git-файлы чистые.
Выполнять только от обычного пользователя, **не через sudo**:

```bash
cd /1tbdisk/PegineLab/projects/YadroKreator
cat /1tbdisk/PegineLab/factory-state/updates.json
git status --short
systemctl --user list-units --all 'peginelab-factory-update-*'
```

Если операция `failed` (не `running`), а файловые изменения отсутствуют,
можно применить одноразовый **SSH recovery** из проверенного GitHub main:

```bash
cd /1tbdisk/PegineLab/projects/YadroKreator
git fetch origin main
git show origin/main:scripts/recover_dashboard_update.sh | bash
```

Скрипт проверяет фиксированный Git origin, ветку `main`, clean checkout,
отсутствие активной сборки, fast-forward и Python venv. Он выполнит тесты
**из каталога проекта**, затем перезапустит **только** панель через systemd.
При сбое попытается вернуть исходный Git SHA. База SQLite, результаты Thingino,
`out/private-sd`, SD-карта и системные NVMe не затрагиваются. После успеха
сохранит предыдущий SHA для кнопки отката.

**Важно:** прочитай скрипт через `git show origin/main:scripts/recover_dashboard_update.sh`
до запуска. Загрузка по GitHub должна быть доверенной. При локальных
изменениях скрипт откажет вместо их перезаписи.

## Диагностика точной ошибки, если восстановление тоже завершится ошибкой

```bash
# Свежие ошибки отдельной задачи обновления из systemd user journal
journalctl --user --since "1 hour ago" --no-pager -o short-iso \
  | grep -E -A 12 -B 5 'peginelab-factory-update-|Traceback|FAILED|ERROR|ModuleNotFoundError'

# Проверка набора тестов из корня Git-репозитория:
cd /1tbdisk/PegineLab/projects/YadroKreator
/1tbdisk/PegineLab/factory-venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v
```

Не запускайте сборку прошивки, чтобы «проверить обновление панели»:
это отдельные задания и разные журналы. Не делайте `git reset --hard` вручную
без проверки состояния и бэкапа рабочих файлов.

См. [Git-деплой](GIT_DEPLOY_RU.md) и [инструкцию по скачиванию SD](SD_DOWNLOAD_RU.md).
