# PegineLab CORE · обновление всех проектов, контроль веток и очистка диска

Huananzhi X79 (`192.168.0.100`), Ubuntu Server 24.04, обычный Linux-пользователь (не `sudo`). Корень `/1tbdisk/PegineLab`.

## Первый запуск на чистой системе

```bash
mkdir -p /1tbdisk/PegineLab/projects
cd /1tbdisk/PegineLab/projects
git clone https://github.com/musikfed/YadroKreator.git
cd YadroKreator
bash bootstrap.sh
```

`bootstrap.sh` автоматически запускает **отдельную** безопасную загрузку 3 соседних проектов: `wificam_T23N`, `wifcam_helper`, `Irila_baikal_v1.0`, затем готовит закреплённый исходник Thingino `9925f46f73b9c39ec8d2a65134b18c94e6fdfb97` и устанавливает веб-панель. Исходники находятся в **разных** `projects/<repo>`; сборочные деревья — в **разных** `build/projects/<repo>`. Необходимо подключение к GitHub, Git, Python и системные зависимости сервера. Если локальная папка уже существует и не является чистым Git checkout нужного репозитория, синхронизация останавливается без замены содержимого.

`install.sh` проверяет IP `192.168.0.100`, привязку к :62404 и установленный Thingino; его нельзя слепо повторять для уже работающей панели. После первой установки используйте существующий обновлятор.

## Обновление после установки — одна команда

```bash
cd /1tbdisk/PegineLab/projects/YadroKreator
# 1) Проверить наличие и локальные ветки без изменения:
bash scripts/sync_core_projects.sh
# 2) Загрузить или быстро перемотать (fast-forward) только 3 соседних проекта:
bash scripts/sync_core_projects.sh --apply
# 3) При необходимости той же командой обновить и сам YadroKreator
#    через его ПРОВЕРЕННЫЙ deploy.sh: тесты → рестарт службы → откат при ошибке.
bash scripts/sync_core_projects.sh --apply --with-factory
```

**Если новая версия `scripts/sync_core_projects.sh` ещё отсутствует в локальном YadroKreator**, сначала обновите панель через вкладку **Система → Проверить → Обновить** или существующую команду `bash deploy.sh --apply`. Этот обновлятор обновляет **только YadroKreator** и не делает `git pull` других репозиториев сам.

Синхронизатор никогда не выполняет `git reset --hard`, `git clean -fdx`, `git checkout -B`, `git push` или прошивку SD. Он проверяет URL `origin`, локальные изменения, активные фабричные задания, текущую ветку и допускает только `git merge --ff-only`. Отсутствующие каталоги клонируются в правильные папки. Никакой локальный код, пароли Wi-Fi, `~/crt-cert/`, IMG или отдельные каталоги сборок не стираются.

**Особый случай WIFICAM:** заводская кнопка **«Собрать WIFICAM»** сама выполняет `git fetch` выбранной ветки (`mymarrchWFcam` либо `main`) в отдельный bare cache, закрепляет Git SHA на задание и собирает именно этот SHA. Для неё предварительный `git pull` исходников **не обязателен**. Локальный `projects/wificam_T23N/local/wifi.env` используется отдельно, если файл существует, и не отправляется в GitHub. WifCam Helper читает локальный файл `profiles/t23n_lean.json`, поэтому его синхронизация нужна. Аудит Irila сам получает SHA из GitHub, но отдельный локальный checkout удобно поддерживать актуальным.

`YadroKreator` не запускает автоматически сборки при обновлении GitHub. Кнопка компиляции — только по решению оператора. В фабрике действует запрет двух одновременных заданий.

## Проверка и удаление старых GitHub-веток

```bash
# Только проверить удалённые ветки и определить, какие полностью входят в main:
bash scripts/prune_merged_branches.sh --project YadroKreator
bash scripts/prune_merged_branches.sh --project wificam_T23N

# Предпросмотр удаления ОДНОЙ конкретной уже слитой ветки:
bash scripts/prune_merged_branches.sh --project YadroKreator \
  --branch feature/dashboard-updates-rollback

# Только после проверки, что она не нужна и целиком включена в main:
bash scripts/prune_merged_branches.sh --project YadroKreator \
  --branch feature/dashboard-updates-rollback \
  --apply --confirm DELETE-MERGED-REMOTE-BRANCHES
```

Защищены `main` во всех репозиториях и **навсегда исключены из удаления** `wificam_T23N/mymarrchWFcam` и `wificam_T23N/release/0.1_test`. Скрипт не удаляет несмерженные ветки или ветки, используемые локально; фиксирует точный SHA и использует `git push --force-with-lease` для защиты от изменения ветки между проверкой и удалением. При удалении требуется право записи в GitHub с Linux-хоста; подключение GitHub к чату **не предоставляет** серверу Git-учётные данные.

**Аудит на 4 ноября 2026:** в `YadroKreator` 13 исторических feature/fix/docs-веток полностью предки `main`, но `feature/one-click-sd-download-browser-login` и `feature/project-service-start-stop-linux-windows` имеют отдельные коммиты и не должны удаляться автоматически. В `wificam_T23N` ветка `feature/peginelab-firmware-factory-62404` целиком вошла в `main`; остальные ветки с незавершёнными изменениями сохраняются. Рабочая `mymarrchWFcam` **на 47 коммитов впереди** относительно части истории `main`; её удаление сейчас сломает запуск по умолчанию. Аппаратный эталон `release/0.1_test` тоже сохраняем.

Серверная команда **не** удаляет ветки без указания их точных имён. Одна ошибка в сторонней ветке не повод терять неперенесённые исправления.

## Очистка файловой базы прежней фабрики

```bash
cd /1tbdisk/PegineLab/projects/YadroKreator

# Только предварительный список старых завершённых заданий и логов:
bash scripts/cleanup_old_results.sh

# Дополнительно ПОКАЗАТЬ старые осиротевшие UUID-деревья, старые
# bare Git-кеши и старые ОБЩИЕ build/cache, build/tmp:
bash scripts/cleanup_old_results.sh --include-orphans \
  --prune-old-git-cache --prune-old-shared-cache

# После внимательной проверки списка — ручное удаление этих категорий:
bash scripts/cleanup_old_results.sh --include-orphans \
  --prune-old-git-cache --prune-old-shared-cache \
  --apply --confirm DELETE-LEGACY-JOBS
```

Удаление запрещено во время активной сборки/обновления панели, при опасных символических ссылках или запуске через `sudo`. В SQLite удаляются лишь записи старых законченных заданий, а не вся база; новые журналы, новое дерево `build/projects/`, `factory-state/factory.sqlite3`, закреплённый Thingino и `projects/wificam_T23N/Thingino/thingino-t23-sd.bin` не входят в план удаления. Старые каталоги `build/jobs/<uuid>` и `factory-state/logs/<uuid>.log` после очистки больше не доступны в панели, что соответствует решению отказаться от архивов.

**Внимание:** GitHub хранит коммиты и только опубликованные бинарные файлы. Локально собранные приватные SD-образы, отчёты, логи и Wi-Fi конфигурация могут **не иметь копии в GitHub**. Скрипт показывает имена удаляемых путей, но не гарантирует их резервную копию. Старый `build/cache` также может потребоваться для других вручную запущенных процессов — проверяйте его использование отдельно.

[Схема разделённых деревьев](MULTI_PROJECT_BUILDS_RU.md) · [Контракт Helper](WIFCAM_HELPER_INTEGRATION_RU.md).
