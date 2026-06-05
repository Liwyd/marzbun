#!/usr/bin/env bash
set -e

# ─────────────────────────────────────────────────────────
#  Marzbun — self-hosted installer
#  Source: https://github.com/Liwyd/marzbun
#
#  One-line install:
#    bash <(curl -sSL https://raw.githubusercontent.com/Liwyd/marzbun/master/install.sh)
# ─────────────────────────────────────────────────────────

APP_NAME="marzbun"
GITHUB_REPO="Liwyd/marzbun"
GITHUB_RAW="https://raw.githubusercontent.com/${GITHUB_REPO}/master"
GITHUB_CLONE="https://github.com/${GITHUB_REPO}.git"

INSTALL_DIR="/opt"
APP_DIR="${INSTALL_DIR}/${APP_NAME}"
DATA_DIR="/var/lib/${APP_NAME}"
COMPOSE_FILE="${APP_DIR}/docker-compose.yml"
ENV_FILE="${APP_DIR}/.env"
SCRIPT_PATH="/usr/local/bin/${APP_NAME}"

# ─── colour helpers ───────────────────────────────────────

colorized_echo() {
    local color=$1 text=$2
    case $color in
        red)     printf "\e[91m%s\e[0m\n" "$text" ;;
        green)   printf "\e[92m%s\e[0m\n" "$text" ;;
        yellow)  printf "\e[93m%s\e[0m\n" "$text" ;;
        blue)    printf "\e[94m%s\e[0m\n" "$text" ;;
        magenta) printf "\e[95m%s\e[0m\n" "$text" ;;
        cyan)    printf "\e[96m%s\e[0m\n" "$text" ;;
        *)       echo "$text" ;;
    esac
}

# ─── OS / arch detection ─────────────────────────────────

detect_os() {
    if [ -f /etc/lsb-release ]; then
        OS=$(lsb_release -si)
    elif [ -f /etc/os-release ]; then
        OS=$(awk -F= '/^NAME/{print $2}' /etc/os-release | tr -d '"')
    elif [ -f /etc/redhat-release ]; then
        OS=$(awk '{print $1}' /etc/redhat-release)
    elif [ -f /etc/arch-release ]; then
        OS="Arch"
    else
        colorized_echo red "Unsupported operating system"
        exit 1
    fi
}

detect_arch() {
    case "$(uname -m)" in
        i386|i686)       ARCH='32'        ;;
        amd64|x86_64)    ARCH='64'        ;;
        armv5tel)        ARCH='arm32-v5'  ;;
        armv6l)          ARCH='arm32-v6'  ;;
        armv7|armv7l)    ARCH='arm32-v7a' ;;
        armv8|aarch64)   ARCH='arm64-v8a' ;;
        mips)            ARCH='mips32'    ;;
        mipsle)          ARCH='mips32le'  ;;
        mips64)          ARCH='mips64'    ;;
        mips64le)        ARCH='mips64le'  ;;
        ppc64)           ARCH='ppc64'     ;;
        ppc64le)         ARCH='ppc64le'   ;;
        riscv64)         ARCH='riscv64'   ;;
        s390x)           ARCH='s390x'     ;;
        *)
            colorized_echo red "Unsupported architecture: $(uname -m)"
            exit 1
            ;;
    esac
}

# ─── package manager ──────────────────────────────────────

detect_and_update_package_manager() {
    colorized_echo blue "Updating package manager"
    if [[ "$OS" == "Ubuntu"* ]] || [[ "$OS" == "Debian"* ]]; then
        PKG_MANAGER="apt-get"
        $PKG_MANAGER update -y
    elif [[ "$OS" == "CentOS"* ]] || [[ "$OS" == "AlmaLinux"* ]] || [[ "$OS" == "Rocky"* ]]; then
        PKG_MANAGER="yum"
        $PKG_MANAGER update -y
        $PKG_MANAGER install -y epel-release
    elif [[ "$OS" == "Fedora"* ]]; then
        PKG_MANAGER="dnf"
        $PKG_MANAGER update -y
    elif [[ "$OS" == "Arch"* ]]; then
        PKG_MANAGER="pacman"
        $PKG_MANAGER -Sy --noconfirm
    elif [[ "$OS" == "openSUSE"* ]]; then
        PKG_MANAGER="zypper"
        $PKG_MANAGER refresh
    else
        colorized_echo red "Unsupported OS for package management: $OS"
        exit 1
    fi
}

install_package() {
    [ -z "$PKG_MANAGER" ] && detect_and_update_package_manager
    local pkg=$1
    colorized_echo blue "Installing $pkg"
    case "$PKG_MANAGER" in
        apt-get) $PKG_MANAGER install -y "$pkg" ;;
        yum|dnf) $PKG_MANAGER install -y "$pkg" ;;
        pacman)  $PKG_MANAGER -S --noconfirm "$pkg" ;;
        zypper)  $PKG_MANAGER install -y "$pkg" ;;
    esac
}

# ─── docker ───────────────────────────────────────────────

install_docker() {
    colorized_echo blue "Installing Docker via official script"
    curl -fsSL https://get.docker.com | sh
    colorized_echo green "Docker installed successfully"
}

detect_compose() {
    if docker compose version >/dev/null 2>&1; then
        COMPOSE='docker compose'
    elif docker-compose version >/dev/null 2>&1; then
        COMPOSE='docker-compose'
    else
        colorized_echo red "docker compose not found — please install Docker Compose v2"
        exit 1
    fi
}

# ─── state helpers ────────────────────────────────────────

check_running_as_root() {
    if [ "$(id -u)" != "0" ]; then
        colorized_echo red "This command must be run as root."
        exit 1
    fi
}

is_installed() {
    [ -d "$APP_DIR" ]
}

is_up() {
    [ -n "$($COMPOSE -f "$COMPOSE_FILE" ps -q -a 2>/dev/null)" ]
}

# ─── core management script installer ────────────────────

install_marzbun_script() {
    colorized_echo blue "Installing ${APP_NAME} management script to ${SCRIPT_PATH}"
    curl -sSL "${GITHUB_RAW}/install.sh" -o "${SCRIPT_PATH}"
    chmod 755 "${SCRIPT_PATH}"
    colorized_echo green "${APP_NAME} script installed at ${SCRIPT_PATH}"
}

# ─── docker-compose.yml generator ────────────────────────

write_compose_sqlite() {
    cat > "$COMPOSE_FILE" <<'EOF'
services:
  marzbun:
    build: .
    restart: always
    env_file: .env
    network_mode: host
    volumes:
      - /var/lib/marzbun:/var/lib/marzban
EOF
}

write_compose_mariadb() {
    cat > "$COMPOSE_FILE" <<'EOF'
services:
  marzbun:
    build: .
    restart: always
    env_file: .env
    network_mode: host
    volumes:
      - /var/lib/marzbun:/var/lib/marzban
      - /var/lib/marzbun/logs:/var/lib/marzban-node
    depends_on:
      mariadb:
        condition: service_healthy

  mariadb:
    image: mariadb:lts
    env_file: .env
    network_mode: host
    restart: always
    environment:
      MYSQL_ROOT_PASSWORD: ${MYSQL_ROOT_PASSWORD}
      MYSQL_ROOT_HOST: '%'
      MYSQL_DATABASE: ${MYSQL_DATABASE}
      MYSQL_USER: ${MYSQL_USER}
      MYSQL_PASSWORD: ${MYSQL_PASSWORD}
    command:
      - --bind-address=127.0.0.1
      - --character_set_server=utf8mb4
      - --collation_server=utf8mb4_unicode_ci
      - --host-cache-size=0
      - --innodb-open-files=1024
      - --innodb-buffer-pool-size=256M
      - --binlog_expire_logs_seconds=1209600
      - --innodb-log-file-size=64M
      - --innodb-log-files-in-group=2
      - --innodb-doublewrite=0
      - --general_log=0
      - --slow_query_log=1
      - --slow_query_log_file=/var/lib/mysql/slow.log
      - --long_query_time=2
    volumes:
      - /var/lib/marzbun/mysql:/var/lib/mysql
    healthcheck:
      test: ["CMD", "healthcheck.sh", "--connect", "--innodb_initialized"]
      start_period: 10s
      start_interval: 3s
      interval: 10s
      timeout: 5s
      retries: 3
EOF
}

write_compose_mysql() {
    cat > "$COMPOSE_FILE" <<'EOF'
services:
  marzbun:
    build: .
    restart: always
    env_file: .env
    network_mode: host
    volumes:
      - /var/lib/marzbun:/var/lib/marzban
      - /var/lib/marzbun/logs:/var/lib/marzban-node
    depends_on:
      mysql:
        condition: service_healthy

  mysql:
    image: mysql:lts
    env_file: .env
    network_mode: host
    restart: always
    environment:
      MYSQL_ROOT_PASSWORD: ${MYSQL_ROOT_PASSWORD}
      MYSQL_ROOT_HOST: '%'
      MYSQL_DATABASE: ${MYSQL_DATABASE}
      MYSQL_USER: ${MYSQL_USER}
      MYSQL_PASSWORD: ${MYSQL_PASSWORD}
    command:
      - --mysqlx=OFF
      - --bind-address=127.0.0.1
      - --character_set_server=utf8mb4
      - --collation_server=utf8mb4_unicode_ci
      - --binlog_expire_logs_seconds=1209600
      - --host-cache-size=0
      - --innodb-open-files=1024
      - --innodb-buffer-pool-size=256M
      - --innodb-log-file-size=64M
      - --general_log=0
      - --slow_query_log=1
      - --slow_query_log_file=/var/lib/mysql/slow.log
      - --long_query_time=2
    volumes:
      - /var/lib/marzbun/mysql:/var/lib/mysql
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "127.0.0.1", "-u", "marzban", "--password=${MYSQL_PASSWORD}"]
      start_period: 5s
      interval: 5s
      timeout: 5s
      retries: 55
EOF
}

# ─── install ──────────────────────────────────────────────

install_command() {
    check_running_as_root

    local database_type="sqlite"

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --database) database_type="$2"; shift 2 ;;
            *) colorized_echo red "Unknown option: $1"; exit 1 ;;
        esac
    done

    if is_installed; then
        colorized_echo red "${APP_NAME} is already installed at ${APP_DIR}"
        read -rp "Override the previous installation? (y/n) " REPLY
        [[ $REPLY =~ ^[Yy]$ ]] || { colorized_echo red "Aborted"; exit 1; }
    fi

    detect_os

    command -v curl  >/dev/null 2>&1 || install_package curl
    command -v git   >/dev/null 2>&1 || install_package git
    command -v jq    >/dev/null 2>&1 || install_package jq
    command -v docker>/dev/null 2>&1 || install_docker
    detect_compose

    # ── clone source ──────────────────────────────────────
    colorized_echo blue "Cloning ${GITHUB_REPO} into ${APP_DIR}"
    if [ -d "$APP_DIR/.git" ]; then
        git -C "$APP_DIR" fetch --all
        git -C "$APP_DIR" reset --hard origin/master
    else
        rm -rf "$APP_DIR"
        git clone --depth 1 "${GITHUB_CLONE}" "$APP_DIR"
    fi
    colorized_echo green "Source code ready at ${APP_DIR}"

    mkdir -p "$DATA_DIR"

    # ── docker-compose.yml ────────────────────────────────
    colorized_echo blue "Generating docker-compose.yml (database: ${database_type})"
    case "$database_type" in
        mariadb) write_compose_mariadb ;;
        mysql)   write_compose_mysql   ;;
        *)       write_compose_sqlite  ; database_type="sqlite" ;;
    esac
    colorized_echo green "Saved ${COMPOSE_FILE}"

    # ── .env ──────────────────────────────────────────────
    colorized_echo blue "Creating .env from template"
    cp "${APP_DIR}/.env.example" "${ENV_FILE}"

    # uncomment XRAY_JSON and point it to the persistent volume path
    sed -i 's|^# \(XRAY_JSON = .*\)$|\1|'  "$ENV_FILE"
    sed -i 's|^\(XRAY_JSON = \).*|\1"/var/lib/marzban/xray_config.json"|' "$ENV_FILE"

    if [ "$database_type" == "sqlite" ]; then
        sed -i 's|^# \(SQLALCHEMY_DATABASE_URL = .*sqlite.*\)$|\1|' "$ENV_FILE"
        sed -i 's|^\(SQLALCHEMY_DATABASE_URL = \).*|\1"sqlite:////var/lib/marzban/db.sqlite3"|' "$ENV_FILE"
    else
        # comment out sqlite line
        sed -i 's|^\(SQLALCHEMY_DATABASE_URL = "sqlite://.*"\)|#\1|' "$ENV_FILE"

        read -rsp "Enter password for the marzban DB user (leave blank to auto-generate): " MYSQL_PASSWORD; echo
        [ -z "$MYSQL_PASSWORD" ] && MYSQL_PASSWORD=$(tr -dc 'A-Za-z0-9' </dev/urandom | head -c 20)
        MYSQL_ROOT_PASSWORD=$(tr -dc 'A-Za-z0-9' </dev/urandom | head -c 20)

        cat >> "$ENV_FILE" <<EOF

# Database configuration
MYSQL_ROOT_PASSWORD=${MYSQL_ROOT_PASSWORD}
MYSQL_DATABASE=marzban
MYSQL_USER=marzban
MYSQL_PASSWORD=${MYSQL_PASSWORD}
SQLALCHEMY_DATABASE_URL="mysql+pymysql://marzban:${MYSQL_PASSWORD}@127.0.0.1:3306/marzban"
EOF
    fi
    colorized_echo green "Saved ${ENV_FILE}"

    # ── copy xray_config.json to data dir ─────────────────
    colorized_echo blue "Copying default xray_config.json to ${DATA_DIR}"
    cp "${APP_DIR}/xray_config.json" "${DATA_DIR}/xray_config.json"
    colorized_echo green "Saved ${DATA_DIR}/xray_config.json"

    # ── build image ───────────────────────────────────────
    colorized_echo blue "Building Docker image (this may take a few minutes)..."
    $COMPOSE -f "$COMPOSE_FILE" -p "$APP_NAME" build --no-cache
    colorized_echo green "Docker image built successfully"

    # ── install management script ─────────────────────────
    install_marzbun_script

    # ── start ─────────────────────────────────────────────
    up_marzbun
    colorized_echo green "════════════════════════════════════"
    colorized_echo green "  ${APP_NAME} installed successfully!"
    colorized_echo cyan  "  Panel:   http://<server-ip>:8000/dashboard/"
    colorized_echo cyan  "  Manage:  ${APP_NAME} [up|down|restart|logs|cli|update|...]"
    colorized_echo green "════════════════════════════════════"
    follow_marzbun_logs
}

# ─── lifecycle helpers ───────────────────────────────────

up_marzbun() {
    $COMPOSE -f "$COMPOSE_FILE" -p "$APP_NAME" up -d --remove-orphans
}

down_marzbun() {
    $COMPOSE -f "$COMPOSE_FILE" -p "$APP_NAME" down
}

show_marzbun_logs() {
    $COMPOSE -f "$COMPOSE_FILE" -p "$APP_NAME" logs
}

follow_marzbun_logs() {
    $COMPOSE -f "$COMPOSE_FILE" -p "$APP_NAME" logs -f
}

marzbun_cli() {
    $COMPOSE -f "$COMPOSE_FILE" -p "$APP_NAME" \
        exec -e CLI_PROG_NAME="${APP_NAME} cli" marzbun marzban-cli "$@"
}

# ─── commands ────────────────────────────────────────────

up_command() {
    local no_logs=false
    while [[ $# -gt 0 ]]; do
        case "$1" in
            -n|--no-logs) no_logs=true ;;
            -h|--help) echo "Usage: ${APP_NAME} up [-n]"; exit 0 ;;
            *) colorized_echo red "Unknown option: $1"; exit 1 ;;
        esac
        shift
    done
    is_installed || { colorized_echo red "${APP_NAME} is not installed"; exit 1; }
    detect_compose
    is_up && { colorized_echo red "${APP_NAME} is already up"; exit 1; }
    up_marzbun
    [ "$no_logs" = false ] && follow_marzbun_logs
}

down_command() {
    is_installed || { colorized_echo red "${APP_NAME} is not installed"; exit 1; }
    detect_compose
    is_up || { colorized_echo red "${APP_NAME} is already down"; exit 1; }
    down_marzbun
}

restart_command() {
    local no_logs=false
    while [[ $# -gt 0 ]]; do
        case "$1" in
            -n|--no-logs) no_logs=true ;;
            -h|--help) echo "Usage: ${APP_NAME} restart [-n]"; exit 0 ;;
            *) colorized_echo red "Unknown option: $1"; exit 1 ;;
        esac
        shift
    done
    is_installed || { colorized_echo red "${APP_NAME} is not installed"; exit 1; }
    detect_compose
    down_marzbun
    up_marzbun
    [ "$no_logs" = false ] && follow_marzbun_logs
    colorized_echo green "${APP_NAME} restarted successfully"
}

status_command() {
    is_installed || { colorized_echo red "${APP_NAME} is not installed"; exit 1; }
    detect_compose
    if ! is_up; then
        echo -n "Status: "; colorized_echo blue "Down"; exit 1
    fi
    echo -n "Status: "; colorized_echo green "Up"
    json=$($COMPOSE -f "$COMPOSE_FILE" ps -a --format=json 2>/dev/null)
    echo "$json" | grep -E '"Service"|"State"' | paste - - | \
        sed 's/.*"Service": "\([^"]*\)".*"State": "\([^"]*\)".*/  \1: \2/'
}

logs_command() {
    local no_follow=false
    while [[ $# -gt 0 ]]; do
        case "$1" in
            -n|--no-follow) no_follow=true ;;
            -h|--help) echo "Usage: ${APP_NAME} logs [-n]"; exit 0 ;;
            *) colorized_echo red "Unknown option: $1"; exit 1 ;;
        esac
        shift
    done
    is_installed || { colorized_echo red "${APP_NAME} is not installed"; exit 1; }
    detect_compose
    is_up || { colorized_echo red "${APP_NAME} is not running"; exit 1; }
    [ "$no_follow" = true ] && show_marzbun_logs || follow_marzbun_logs
}

cli_command() {
    is_installed || { colorized_echo red "${APP_NAME} is not installed"; exit 1; }
    detect_compose
    is_up || { colorized_echo red "${APP_NAME} is not running"; exit 1; }
    marzbun_cli "$@"
}

update_command() {
    check_running_as_root
    is_installed || { colorized_echo red "${APP_NAME} is not installed"; exit 1; }
    detect_compose

    colorized_echo blue "Pulling latest source from GitHub"
    git -C "$APP_DIR" fetch --all
    git -C "$APP_DIR" reset --hard origin/master
    colorized_echo green "Source updated"

    colorized_echo blue "Rebuilding Docker image"
    $COMPOSE -f "$COMPOSE_FILE" -p "$APP_NAME" build
    colorized_echo green "Image rebuilt"

    colorized_echo blue "Restarting services"
    down_marzbun
    up_marzbun
    colorized_echo green "${APP_NAME} updated and restarted successfully"

    # refresh management script from updated repo
    colorized_echo blue "Updating management script"
    install -m 755 "${APP_DIR}/install.sh" "${SCRIPT_PATH}"
    colorized_echo green "Management script updated"
}

uninstall_command() {
    check_running_as_root
    is_installed || { colorized_echo red "${APP_NAME} is not installed"; exit 1; }

    read -rp "Really uninstall ${APP_NAME}? (y/n) " REPLY
    [[ $REPLY =~ ^[Yy]$ ]] || { colorized_echo red "Aborted"; exit 1; }

    detect_compose
    is_up && down_marzbun

    # remove built images
    local images
    images=$(docker images | grep "$APP_NAME" | awk '{print $3}')
    for img in $images; do
        docker rmi "$img" >/dev/null 2>&1 && colorized_echo yellow "Removed image $img"
    done

    rm -rf "$APP_DIR"
    rm -f  "$SCRIPT_PATH"
    colorized_echo green "${APP_NAME} uninstalled (app files removed)"

    read -rp "Also delete data directory ${DATA_DIR}? (y/n) " REPLY
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -rf "$DATA_DIR"
        colorized_echo green "Data directory removed"
    fi
    colorized_echo green "Done"
}

edit_command() {
    detect_os; check_editor
    [ -f "$COMPOSE_FILE" ] && $EDITOR "$COMPOSE_FILE" || {
        colorized_echo red "Compose file not found: ${COMPOSE_FILE}"; exit 1
    }
}

edit_env_command() {
    detect_os; check_editor
    [ -f "$ENV_FILE" ] && $EDITOR "$ENV_FILE" || {
        colorized_echo red "Env file not found: ${ENV_FILE}"; exit 1
    }
}

check_editor() {
    if [ -z "$EDITOR" ]; then
        if   command -v nano >/dev/null 2>&1; then EDITOR="nano"
        elif command -v vi   >/dev/null 2>&1; then EDITOR="vi"
        else detect_os; install_package nano; EDITOR="nano"
        fi
    fi
}

# ─── xray core management ────────────────────────────────

get_xray_core() {
    detect_arch
    local latest_releases versions selected_version

    latest_releases=$(curl -s "https://api.github.com/repos/XTLS/Xray-core/releases?per_page=10")
    mapfile -t versions < <(echo "$latest_releases" | grep -oP '"tag_name": "\K[^"]+')

    echo -e "\033[1;32m==============================\033[0m"
    echo -e "\033[1;32m    Xray-core Version Menu    \033[0m"
    echo -e "\033[1;32m==============================\033[0m"
    for i in "${!versions[@]}"; do
        printf "\033[1;34m%2d\033[0m: %s\n" "$((i+1))" "${versions[$i]}"
    done
    echo -e "\033[1;35mM\033[0m: Enter version manually"
    echo -e "\033[1;31mQ\033[0m: Quit"
    echo -e "\033[1;32m==============================\033[0m"

    while true; do
        read -rp "Choose (1-${#versions[@]}, M, Q): " choice
        if [[ "$choice" =~ ^[0-9]+$ ]] && (( choice >= 1 && choice <= ${#versions[@]} )); then
            selected_version="${versions[$((choice-1))]}"
            break
        elif [[ "$choice" =~ ^[Mm]$ ]]; then
            read -rp "Enter version (e.g. v1.8.24): " selected_version
            break
        elif [[ "$choice" =~ ^[Qq]$ ]]; then
            exit 0
        fi
    done

    colorized_echo blue "Installing Xray-core ${selected_version}"
    command -v unzip >/dev/null 2>&1 || { detect_os; install_package unzip; }
    command -v wget  >/dev/null 2>&1 || { detect_os; install_package wget;  }

    mkdir -p "${DATA_DIR}/xray-core"
    local zip="Xray-linux-${ARCH}.zip"
    wget -q -O "/tmp/${zip}" \
        "https://github.com/XTLS/Xray-core/releases/download/${selected_version}/${zip}"
    unzip -o "/tmp/${zip}" xray geoip.dat geosite.dat -d "${DATA_DIR}/xray-core" >/dev/null 2>&1
    chmod +x "${DATA_DIR}/xray-core/xray"
    rm "/tmp/${zip}"
    colorized_echo green "Xray-core ${selected_version} installed at ${DATA_DIR}/xray-core/xray"
}

update_core_command() {
    check_running_as_root
    get_xray_core
    local xray_path="${DATA_DIR}/xray-core/xray"
    local line="XRAY_EXECUTABLE_PATH=\"${xray_path}\""
    if grep -q "^XRAY_EXECUTABLE_PATH=" "$ENV_FILE"; then
        sed -i "s|^XRAY_EXECUTABLE_PATH=.*|${line}|" "$ENV_FILE"
    else
        echo "${line}" >> "$ENV_FILE"
    fi
    colorized_echo blue "Restarting ${APP_NAME} with new core..."
    restart_command -n
    colorized_echo green "Xray core updated and ${APP_NAME} restarted"
}

# ─── backup ───────────────────────────────────────────────

add_cron_job() {
    local schedule="$1" command="$2"
    local tmp; tmp=$(mktemp)
    crontab -l 2>/dev/null > "$tmp" || true
    grep -v "$command" "$tmp" > "${tmp}.new" && mv "${tmp}.new" "$tmp"
    echo "$schedule $command # ${APP_NAME}-backup" >> "$tmp"
    crontab "$tmp" && colorized_echo green "Cron job added"
    rm -f "$tmp"
}

remove_backup_service() {
    sed -i '/^# Backup service configuration/d' "$ENV_FILE"
    sed -i '/BACKUP_SERVICE_ENABLED/d'          "$ENV_FILE"
    sed -i '/BACKUP_TELEGRAM_BOT_KEY/d'         "$ENV_FILE"
    sed -i '/BACKUP_TELEGRAM_CHAT_ID/d'         "$ENV_FILE"
    sed -i '/BACKUP_CRON_SCHEDULE/d'            "$ENV_FILE"
    local tmp; tmp=$(mktemp)
    crontab -l 2>/dev/null > "$tmp" || true
    sed -i "/${APP_NAME}-backup/d" "$tmp"
    crontab "$tmp" && colorized_echo green "Backup cron removed"
    rm -f "$tmp"
    colorized_echo green "Backup service removed"
}

send_backup_to_telegram() {
    # load env vars
    set -a; source "$ENV_FILE"; set +a
    [ "$BACKUP_SERVICE_ENABLED" = "true" ] || {
        colorized_echo yellow "Backup service not enabled"; return
    }
    local server_ip backup_path
    server_ip=$(curl -s ifconfig.me 2>/dev/null || echo "Unknown")
    backup_path=$(ls -t "${APP_DIR}/backup" 2>/dev/null | head -1)
    [ -z "$backup_path" ] && { colorized_echo red "No backups found"; return; }
    backup_path="${APP_DIR}/backup/${backup_path}"

    local split_dir="/tmp/${APP_NAME}_backup_split"
    mkdir -p "$split_dir"
    local size; size=$(du -m "$backup_path" | cut -f1)
    if (( size > 49 )); then
        split -b 49M "$backup_path" "${split_dir}/part_"
    else
        cp "$backup_path" "${split_dir}/part_aa"
    fi

    local ts; ts=$(date "+%Y-%m-%d %H:%M:%S %Z")
    for part in "${split_dir}"/*; do
        local fname="backup_$(basename "$part").tar.gz"
        curl -s \
            -F chat_id="$BACKUP_TELEGRAM_CHAT_ID" \
            -F "document=@${part};filename=${fname}" \
            -F caption="📦 Server: ${server_ip} | Time: ${ts}" \
            "https://api.telegram.org/bot${BACKUP_TELEGRAM_BOT_KEY}/sendDocument" >/dev/null \
            && colorized_echo green "Sent ${fname}" \
            || colorized_echo red "Failed to send ${fname}"
    done
    rm -rf "$split_dir"
}

backup_command() {
    local backup_dir="${APP_DIR}/backup"
    local tmp_dir="/tmp/${APP_NAME}_backup"
    local ts; ts=$(date +"%Y%m%d%H%M%S")
    local archive="${backup_dir}/backup_${ts}.tar.gz"

    command -v rsync >/dev/null 2>&1 || { detect_os; install_package rsync; }
    rm -rf "$backup_dir"; mkdir -p "$backup_dir" "$tmp_dir"

    cp "$ENV_FILE"      "$tmp_dir/"
    cp "$COMPOSE_FILE"  "$tmp_dir/"

    # copy xray config and sqlite db
    rsync -a --exclude='xray-core' --exclude='mysql' \
        "${DATA_DIR}/" "${tmp_dir}/marzbun_data/" 2>/dev/null || true

    tar -czf "$archive" -C "$tmp_dir" .
    rm -rf "$tmp_dir"
    colorized_echo green "Backup created: ${archive}"
    send_backup_to_telegram
}

backup_service_command() {
    if grep -q "BACKUP_SERVICE_ENABLED=true" "$ENV_FILE" 2>/dev/null; then
        colorized_echo cyan "Backup is already configured. Options:"
        echo "1. Reconfigure  2. Remove  3. Exit"
        read -rp "Choice: " c
        case $c in
            1) remove_backup_service ;;
            2) remove_backup_service; return ;;
            3) return ;;
        esac
    fi

    read -rp "Telegram bot API key: " tg_key
    read -rp "Telegram chat ID: "    tg_chat
    read -rp "Backup interval in hours (1-24): " hours
    local schedule
    (( hours == 24 )) && schedule="0 0 * * *" || schedule="0 */${hours} * * *"

    {
        echo ""
        echo "# Backup service configuration"
        echo "BACKUP_SERVICE_ENABLED=true"
        echo "BACKUP_TELEGRAM_BOT_KEY=${tg_key}"
        echo "BACKUP_TELEGRAM_CHAT_ID=${tg_chat}"
        echo "BACKUP_CRON_SCHEDULE=\"${schedule}\""
    } >> "$ENV_FILE"

    add_cron_job "$schedule" "$(command -v bash) -c '${APP_NAME} backup'"
    colorized_echo green "Backup service configured — every ${hours}h"
}

# ─── install-script (standalone re-install of CLI only) ──

install_script_command() {
    check_running_as_root
    install_marzbun_script
}

# ─── usage ───────────────────────────────────────────────

usage() {
    colorized_echo blue "══════════════════════════════════════════"
    colorized_echo magenta "             Marzbun Manager"
    colorized_echo blue "══════════════════════════════════════════"
    colorized_echo cyan "Usage:  ${APP_NAME} <command> [options]"
    echo
    colorized_echo cyan "Commands:"
    colorized_echo yellow "  install         – Install Marzbun (builds from source)"
    colorized_echo yellow "  update          – Pull latest source & rebuild"
    colorized_echo yellow "  uninstall       – Remove Marzbun"
    colorized_echo yellow "  up              – Start services"
    colorized_echo yellow "  down            – Stop services"
    colorized_echo yellow "  restart         – Restart services"
    colorized_echo yellow "  status          – Show container status"
    colorized_echo yellow "  logs            – Follow logs  (-n to print & exit)"
    colorized_echo yellow "  cli             – Run marzban-cli inside the container"
    colorized_echo yellow "  edit            – Edit docker-compose.yml"
    colorized_echo yellow "  edit-env        – Edit .env"
    colorized_echo yellow "  core-update     – Install/switch Xray core version"
    colorized_echo yellow "  backup          – Create a manual backup"
    colorized_echo yellow "  backup-service  – Configure automatic Telegram backups"
    colorized_echo yellow "  install-script  – Re-install this management script"
    colorized_echo yellow "  help            – Show this message"
    echo
    colorized_echo cyan "Directories:"
    colorized_echo magenta "  App:  ${APP_DIR}"
    colorized_echo magenta "  Data: ${DATA_DIR}"
    colorized_echo blue "══════════════════════════════════════════"
}

# ─── dispatcher ──────────────────────────────────────────

case "${1:-}" in
    install)        shift; install_command        "$@" ;;
    update)         shift; update_command         "$@" ;;
    uninstall)      shift; uninstall_command      "$@" ;;
    up)             shift; up_command             "$@" ;;
    down)           shift; down_command           "$@" ;;
    restart)        shift; restart_command        "$@" ;;
    status)         shift; status_command         "$@" ;;
    logs)           shift; logs_command           "$@" ;;
    cli)            shift; cli_command            "$@" ;;
    edit)           shift; edit_command           "$@" ;;
    edit-env)       shift; edit_env_command       "$@" ;;
    core-update)    shift; update_core_command    "$@" ;;
    backup)         shift; backup_command         "$@" ;;
    backup-service) shift; backup_service_command "$@" ;;
    install-script) shift; install_script_command "$@" ;;
    help|"")        usage ;;
    *)
        # When invoked directly as the one-liner installer, no sub-command
        # is passed — run install automatically.
        if [ "$0" = "bash" ] || [[ "$0" == /dev/fd/* ]] || [[ "$0" == /proc/self/fd/* ]]; then
            install_command "$@"
        else
            colorized_echo red "Unknown command: ${1}"
            usage
            exit 1
        fi
        ;;
esac
