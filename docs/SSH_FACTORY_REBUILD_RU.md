# YadroKreator: полная пересборка из Git через SSH (не из браузера)

Выполняется на Ubuntu 24.04 CORE, обычным пользователем `user` (НЕ `sudo`). У YadroKreator **нет обязательных Docker-контейнеров**: код — Flask/Waitress; сборки — изолированные user-systemd задания; данные — отдельная `factory-state/factory.sqlite3`.

## Для первого обновления с прежней версии

```bash
cd /1tbdisk/PegineLab/projects/YadroKreator
bash scripts/project-control.sh status
git status --short

# Получить новую реализацию скрипта с GitHub, не обрывая работу в браузере:
bash deploy.sh --check
bash deploy.sh --apply
```

Во второй команде выполняется уже проверенное обновление фабрики с тестами, перезапуском и предусмотренным откатом Git SHA. Не выполняй при активных заданиях сборки; скрипт должен сам отказать.

## Штатный сценарий обновления и полной пересборки

```bash
cd /1tbdisk/PegineLab/projects/YadroKreator

# Обзор без удаления и перезапуска:
bash scripts/rebuild-from-git.sh --check

# GitHub main → проверка SQLite → backup → зависимости → ВСЕ тесты
# → опциональная очистка только кэша фабрики → рестарт ТОЛЬКО фабрики → HTTP check:
bash scripts/rebuild-from-git.sh --apply --clean-cache
```

**Что делает `--clean-cache`:** только `/1tbdisk/PegineLab/build/projects/YadroKreator/cache/pip` и `__pycache__` внутри исходников панели. Buildroot, Thingino, `out/`, `factory-state/`, Git-кэш WIFICAM, сохранённые microSD-образы и модельные веса не удаляются.

Сценарий создаёт копию `factory.sqlite3` через SQLite backup API в `factory-state/backups/factory-*.sqlite3` и проверяет её целостность. Он не очищает истории сборок и не перестраивает ядро T23N. Системные задания не прерывает. Счётчик, прогресс и логи сборок остаются привязаны к исходному профилю.

Если `--check` или `--apply` жалуются на незакоммиченные файлы, неверную ветку/remote или активный job — сначала разберись с препятствием. **Не использовать `git reset --hard`, `git clean -fdx`, `docker system prune`, `docker volume prune` вручную.**

## Отдельный WifCam Helper

После объединения изменений в `musikfed/wifcam_helper/main` (не до этого):

```bash
cd /1tbdisk/PegineLab/projects/YadroKreator
bash scripts/update_wifcam_helper.sh --apply

cd /1tbdisk/PegineLab/projects/wifcam_helper
bash scripts/install-user-service.sh --start
bash scripts/helper-service.sh status
```

Это только отдельный `peginelab-wifcam-helper.service`. Слушает `127.0.0.1:8765`; из Acer через локальный SSH-туннель:

```powershell
ssh -N -L 8765:127.0.0.1:8765 user@192.168.0.100
```

Открыть на Acer `http://127.0.0.1:8765`. В фабрике отдельная вкладка Helper показывает SHA, собственную SQLite истории тестов и состояние сервиса; **не** отправляет автоматически на вкладку прошивки.

## Какие базы независимы

| Функция | Каталог или база |
| --- | --- |
| Фабрика, журналы и прогресс | `/1tbdisk/PegineLab/factory-state/factory.sqlite3` |
| Сборка WIFICAM | `/1tbdisk/PegineLab/build/projects/wificam_T23N/` |
| WifCam Helper: история проверок | `~/.local/state/wifcam-helper/history.sqlite3` |
| ACHEWIW: рассказы, книги, генерации | `/1tbdisk/achewiw/data/achewiw.sqlite3` |

**Удаление старых рассказов и книг выполняется ТОЛЬКО собственным скриптом ACHEWIW и после создания бэкапа**. Оно не относится к YadroKreator.

## Проверка после пересборки

```bash
systemctl --user is-active peginelab-factory.service
curl -fsS http://192.168.0.100:62404/api/panel/service
curl -fsS http://192.168.0.100:62404/api/helper/status
bash scripts/project-control.sh status
```

Если восстановление неудачное, отдельный существующий скрипт `bash deploy.sh --rollback` предусмотрен для отката предыдущего успешного Git SHA и не отменяет записи SQLite. Не трогать вручную сервисы или контейнеры ACHEWIW/Hombo3.
