# PegineLab Project Contract v1 — единый протокол проектов

YadroKreator работает как инженерная фабрика с двумя режимами: **сборка ядра/прошивки** и **наблюдение за собственным проектом**. Подключение GitHub — только вручную. Никакого автоматического импорта всех репозиториев.

## Подключение

1. В «Система → GitHub-проекты» выбери репозиторий musikfed, ветку, имя, короткий ID и роль.
2. «Наблюдение» добавляет собственную вкладку с GitHub и статусом. Для настоящих метрик нужен утверждённый адаптер мониторинга. Режим НЕ запускает сборку.
3. «Кандидат на сборку» требует файл peginelab.project.json в корне выбранной ветки. Фабрика проверяет Git SHA, получает только JSON с привязкой к SHA, проверяет схему и пути (максимум 32 KiB). Никакой код из Git при проверке не исполняется.
4. Контракт отображает архитектуру, toolchain, целевое оборудование, ожидаемые выходные файлы и заявленный адаптер. **Статус остаётся pending_adapter до ревью и интеграции исполняемого адаптера в саму фабрику.** JSON не даёт права выполнить произвольный скрипт, команды Docker или sudo.
5. Только после добавления и тестирования адаптера ядра появляются реальные кнопки «Собрать», «Проверить», «Скачать» для данного нового профиля. Штатный WIFICAM T23N уже собирается через встроенный профиль и сохраняет прежнюю независимую работоспособность.

## Пример 1: прошивка T23N

```json
{
  "schema": "peginelab.project.v1",
  "project": {
    "name": "WIFICAM T23N",
    "repository": "musikfed/wificam_T23N",
    "branch": "mymarrchWFcam",
    "mode": "build"
  },
  "description": "Ingenic T23N, SC2336, ATBM6012BX; SD boot",
  "platform": {
    "architecture": "mipsel",
    "board": "GV-T23-PTZ-MAIN-V2.0",
    "toolchain": "OpenIPC Buildroot MIPS musl"
  },
  "targets": [
    "t23n_sd"
  ],
  "pipeline": {
    "adapter": "t23n_sd",
    "entrypoint": "scripts/build_thingino_wificam_image.sh"
  },
  "outputs": [
    {
      "type": "img",
      "path": "out/candidate-sd/thingino-t23-sd.bin"
    }
  ],
  "monitoring": {
    "signals": [
      "build_status",
      "artifact_sha256"
    ]
  },
  "docs": [
    "README.md"
  ],
  "extensions": {
    "peginelab.camera": {
      "sensor": "SC2336",
      "wifi": "ATBM6012BX"
    }
  }
}
```

## Пример 2: наблюдение за Helper

```json
{
  "schema": "peginelab.project.v1",
  "project": {
    "name": "WifCam Helper",
    "repository": "musikfed/wifcam_helper",
    "branch": "main",
    "mode": "observe"
  },
  "description": "RTSP / audio diagnostics, not a kernel compiler",
  "platform": {
    "architecture": "x86_64",
    "board": "Huananzhi X79",
    "toolchain": ""
  },
  "targets": [
    "camera_test_bench"
  ],
  "outputs": [
    {
      "type": "report",
      "path": "reports/diagnostic.json"
    }
  ],
  "monitoring": {
    "signals": [
      "service_state",
      "test_count",
      "last_test"
    ]
  },
  "docs": [
    "README.md"
  ],
  "extensions": {
    "peginelab.helper": {
      "bind": "127.0.0.1:8765"
    }
  }
}
```

Примеры — **шаблоны контракта**, не утверждение, что эти файлы уже существуют в названных репозиториях. Чтобы использовать шаблон как контракт, добавь соответствующий JSON в корень ветки GitHub и проверь его.

## Свободные, но определённые правила

**Обязательные поля:** schema, project (name, repository, branch, mode). Для mode=build дополнительно pipeline.adapter и outputs (тип + относительный путь). Все другие настройки необязательны: platform (architecture, board, toolchain), targets, docs, monitoring.signals, description.

**Расширения:** все нестандартные свойства разрешены в extensions с ключом vendor.feature, например peginelab.camera. Так новые проекты развиваются без несовместимости с базовым форматом.

**Скрипты и артефакты:** pipeline.entrypoint — только описательное имя файла в Git, без выполнения. Проверка путей запрещает traversal, абсолютные, скрытые и опасные пути. Контракт сам по себе не включает командные рецепты.

**Метрики:** monitoring.signals — название реальных будущих сигналов, а не фиктивная работающая телеметрия. Мониторинг, healthcheck, логи и повторные сборки требуют проверенных адаптеров.

**Безопасность:** никаких персональных Wi-Fi-настроек, секретов, паролей или токенов в публичном Git. Доступ к подключению — только доверенная LAN/VPN. Не открывать 62404 в WAN.

**Изоляция:** каждому профилю положены отдельные source SHA, рабочая директория, кеш, журнал, системная служба, история и валидатор выходного образа. Никакого общего docker system prune и удаления чужих данных.

## Проверка без компиляции

```bash
python3 scripts/validate-project-contract.py --repo musikfed/wificam_T23N --branch mymarrchWFcam --mode build --manifest /path/to/peginelab.project.json
```

Эта проверка читает только указанный файл и ничего не компилирует.
