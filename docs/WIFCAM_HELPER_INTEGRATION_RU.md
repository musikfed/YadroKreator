# YadroKreator ↔ WifCam Helper: контракт локальной сборки

## Где находятся проекты

На Huananzhi X79 / Ubuntu 24.04:
```text
/1tbdisk/PegineLab/
  projects/
    YadroKreator/       <- фабрика, Flask, systemd user job, SQLite
    wificam_T23N/       <- исходники прошивки/ядра и эталон SD
    wifcam_helper/      <- отдельные тесты RTSP/микрофона/динамика
  build/thingino-firmware/ <- закреплённый upstream Thingino/Buildroot
  build/projects/wificam_T23N/jobs/<job_id>/wificam_T23N/  <- SHA-закреплённый исходник и образ
```
Видео/аудио испытания выполняет Helper на CORE по локальному RTSP/SSH. Он **не** изменяет ядро, GPIO и конфигурацию камеры. Программы `ffmpeg`, `ffprobe`, `ssh` работают на CORE; динамик T23N вызывает локальный `rac` через проверенный `play`.

## Передача профиля в фабрику

Стенд хранит только разрешённый пресет `projects/wifcam_helper/profiles/t23n_lean.json`:
`schema=peginelab.wifcam-helper.build-preset.v1`, камера `galayou_g2_t23n_sc2336_atbm6012bx`, ветка `mymarrchWFcam`, `build_env.WIFICAM_WEBRTC=0|1`.
Никаких произвольных опций Makefile, shell, адресов Git, паролей Wi-Fi, внешних команд и `PUBLISH=1` нет.

Во вкладке «Сборки» ставьте галочку **«Использовать утверждённый профиль WifCam Helper»** только когда нужен этот пресет. API принимает `helper_preset: true`; по умолчанию false. Фабрика читает локальный профиль, проверяет allowlist и сохраняет отдельный неизменяемый снимок `build/projects/wificam_T23N/jobs/<job_id>/helper-preset.json` с правами 0600. Worker повторно проверяет снимок и передаёт *только* разрешённый WIFICAM_WEBRTC в закреплённую сборку WIFICAM. Никакого прямого импорта Python-кода Helper.

**Ядро:** остаётся закреплённая Thingino/Buildroot-конфигурация профиля T23N из WIFICAM. Нельзя считать, что Helper генерирует и устанавливает собственные .config автоматически. Видеопрофиль кодека/битрейта сначала фиксируется по измерениям и физическим тестам; любые изменения kernel config должны проходить отдельный reviewed commit в wificam_T23N.

## Запуск на Ubuntu CORE

```bash
cd /1tbdisk/PegineLab/projects
git clone https://github.com/musikfed/wifcam_helper.git
cd wifcam_helper
bash scripts/verify-host.sh
uv run --no-project python3 -m wifcam_helper web
# Только 127.0.0.1:8765, удалённо — SSH-туннель
```

Python 3.12.3 и uv 0.12.0 подходят для стандартного стенда, установка ML-пакетов необязательна. GPU RTX 3060 может использоваться позже для локального YOLO/Whisper/TTS, но стенд не включает/выключает питание GPU и не запускает Ollama. Для классификации только доверенная локальная модель с явно включённым согласием.

`~/crt-cert/fullchain.pem` и `~/crt-cert/privkey.pem` не трогать: сертификаты — вне проектов; HTTPS можно настроить в отдельном reverse proxy с нормальными правами. Никогда не коммитить privkey.

## Критерии готовности

Github CI Helper/Factory проверяет код, но **не** устройство. После физического холодного запуска образа нужно подтвердить SD, RTSP CH0, доступность микрофонной дорожки, слышимый сигнал штатного динамика, PTZ, Wi-Fi/SSH, CGI :8090 и раздельное включение режима LLM. Измерения задержки «от объектива до экрана» делать аппаратным методом, а не на основании RTT и FPS декодирования.

## Защита от подмены кандидата эталоном 0.1_test

Успешное задание YadroKreator при `PUBLISH=0` должно создать **новый** `out/candidate-sd/thingino-t23-sd.bin` либо `out/private-sd/thingino-t23-sd.bin` (при локальном Wi-Fi профиле) и файл `.sha256` рядом. Если этих файлов нет, задание не считается успешно подготовившим прошивку. Эталон `Thingino/thingino-t23-sd.bin` внутри Git checkout не считается результатом сборки и никогда не выдаётся кнопкой скачивания кандидата.

Перед записью реальной microSD выполнить «Проверить образ перед записью SD»: SHA256, MBR, MSPL LBA34, FAT16 BOOT/uImage LBA2048 и ext4 ROOTFS LBA34816. После загрузки отдельно проверить реальную камеру: SD boot, Wi-Fi/SSH, Web UI :8090 и CGI, RTSP/video, микрофон, динамик, PTZ, ночной режим. WifCam Helper проверяет аудио/видео с CORE, не выполняет прошивку. Rufus/Etcher должны писать **полный raw-образ на microSD с LBA0**, а не создавать установочную USB для ПК. Сохранить исходную рабочую карту для отката.
