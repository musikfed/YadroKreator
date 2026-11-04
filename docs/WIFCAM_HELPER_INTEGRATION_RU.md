# WifCam Helper — отдельная SD-прошивка головы ассистента

## Что это

WifCam Helper — третий самостоятельный сборочный профиль YadroKreator (`t23n_helper_sd`), **а не переключатель для обычной WIFICAM** и не только Python-сервис. Конечное устройство: Ingenic T23N, SC2336, микрофон и динамик камеры. 64 МБ RAM недостаточно для полноразмерной локальной LLM, поэтому RTSP/audio-транспорт остаётся на камере, а CV/STT/LLM/TTS/память должны работать на CORE Huananzhi. Реальную двустороннюю связь проверяем отдельно, не выдаём наличие CGI за готового собеседника.

## GitHub-источники и сборка

1. YadroKreator получает `musikfed/wifcam_helper/main` в отдельный SHA-закреплённый Git worktree.
2. В том же **изолированном job** получает одобренную базу `musikfed/wificam_T23N/mymarrchWFcam` с другим Git SHA. Обе версии фиксирует `source-pins.json` и журнал.
3. Копирует только четыре строго разрешённых файла `firmware/overlay` Helper в `rootfs` базы WIFICAM (проверяет тип, symlink и размер файлов). Ни один Python-модуль Helper на камеру не переносится; никакие произвольные shell-сценарии из Helper на сборочном сервере не исполняются.
4. Выполняет существующий Thingino/Buildroot SD pipeline с `PUBLISH=0`, проверяет новый `out/candidate-sd/thingino-t23-sd.bin` с `.sha256`. Если изображения нет или сборка упала — выдаётся **ошибка**, а не эталон.
5. В той же вкладке можно проверить SD: SHA256, MBR, MSPL LBA34, FAT16 /uImage, ext4 и реальное присутствие отличительного `PEGINELAB_HELPER_FIRMWARE_V1`, CGI и идентификатора интерфейса Helper в корневом ext4. При скачивании контроль повторяется; SD не прошивается автоматически.

## Структура

```text
/1tbdisk/PegineLab/
  projects/YadroKreator/                # сборщик и веб-интерфейс
  projects/wifcam_helper/               # Git прошивочной надстройки и Python-стенда
  projects/wificam_T23N/                # базовый проект + защищённый 0.1_test
  build/thingino-firmware/              # закреплённый Thingino
  build/projects/wifcam_helper/
    git-cache/{wifcam_helper.git,wificam_T23N.git}
    jobs/<UUID>/
      wifcam_helper/firmware/overlay/    # Helper исходник, отдельный SHA
      wificam_T23N/rootfs/              # отдельная сборка базы + overlay
      wificam_T23N/out/candidate-sd/    # новый SD IMG, НЕ baseline
      source-pins.json                  # SHA Helper + WIFICAM
  factory-state/projects/wifcam_helper/
    logs/<UUID>.log
    validation/<UUID>.json
```

Диспетчер не смешивает артефакты и журнал Helper с WIFICAM. Одна общая SQLite отслеживает задания и блокирует одновременные тяжёлые сборки. Удаление конкретного образа по кнопке не удаляет SQLite, Git, лог или защищённый `Thingino/thingino-t23-sd.bin`.

## Реальные возможности надстройки на камере

- `/etc/wifcam-helper-release` — отличимый маркер прошивки.
- `/etc/init.d/S92wifcam-helper` — лёгкая отметка старта без автоматической записи микрофона.
- `/usr/bin/wifcam-helper-probe` — фактическое наличие аудио/видео команд `rad`, `rac`, `rvd`.
- `/cgi-bin/helper-capabilities` — JSON интерфейс для CORE через действующий WIFICAM CGI/httpd и его авторизацию.

**Не реализовано автоматически:** распознавание объектов в беседе, визуальная память, речевая маршрутизация с Ollama, управление VRAM и ответы голосом. Это интеграционный этап CORE ↔ камера после проверки аппаратных трактов. Никакие показатели FPS/слышимости/качества без измерений не обещаются.

## Испытания после Rufus

Скачать прошивку в YadroKreator, записать весь диск с LBA0 на SD через Rufus/Etcher. Не писать MSPL отдельно по seek=34 — он уже внутри IMG. После включения проверить последовательность: SD boot → SSH/Wi-Fi → RTSP → `/cgi-bin/helper-capabilities` → слышимый звук из динамика → фактический аудиосигнал микрофона → SC2336/день/ночь/PTZ → передачу на CORE.

Python-стенд испытаний Helper остался на Huananzhi в том же Git-репозитории, собственная база `~/.local/state/wifcam-helper/history.sqlite3`, локальная веб-панель `127.0.0.1:8765`. Управление стендом находится в раскрывающемся блоке **«Аппаратный испытательный стенд»** внутри сборочной страницы Helper; отдельного пункта меню «Инструменты и сервисы» нет.

## Обновление фабрики из GitHub

После зелёного CI, мержа и при отсутствии текущих сборок (не через веб-обновлятор):

```bash
cd /1tbdisk/PegineLab/projects/YadroKreator
bash scripts/rebuild-from-git.sh --check
bash scripts/rebuild-from-git.sh --apply --clean-cache
```

Сценарий резервирует SQLite и реестр, обновляет только YadroKreator, переустанавливает зависимости/проверяет тесты, удаляет только проектный Python/pip-кэш и перезапускает `peginelab-factory.service`. Для Helper-сборки нет необходимости сначала делать `git pull` в локальном каталоге Helper — worker забирает актуальный `main` сам и фиксирует SHA. Другие проекты, Docker, ACHEWIW, Ollama и восстановительный SD-эталон не трогаются.
