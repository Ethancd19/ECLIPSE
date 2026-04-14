#!/usr/bin/env bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PICO_SDK_PATH_DEFAULT="${PICO_SDK_PATH:-$HOME/pico-sdk}"
STM32CUBE_F4_PATH_DEFAULT="${STM32CUBE_F4_PATH:-$HOME/stm32cubeF4}"
NRF5_SDK_PATH_DEFAULT="${NRF5_SDK_PATH:-$HOME/nRF5_SDK}"
PICO_TOOL_PREFIX="${HOME}/.local"
SUDOERS_FILE="/etc/sudoers.d/orbit"
PICOTOOL_REPO_URL="https://github.com/raspberrypi/picotool.git"

APT_PACKAGES=(
  build-essential
  cmake
  gcc-arm-none-eabi
  git
  libnewlib-arm-none-eabi
  libstdc++-arm-none-eabi-newlib
  libusb-1.0-0-dev
  ninja-build
  openocd
  pkg-config
  python3
  python3-pip
  python3-venv
  usbutils
)

info() {
  printf '[setup] %s\n' "$1"
}

append_line_if_missing() {
  local line="$1"
  local file="$2"

  touch "$file"
  if ! grep -Fqx "$line" "$file"; then
    printf '%s\n' "$line" >> "$file"
  fi
}

ensure_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    printf '[setup] Missing required command: %s\n' "$1" >&2
    exit 1
  fi
}

install_apt_dependencies() {
  ensure_command sudo
  ensure_command apt-get

  info "Installing Ubuntu packages needed for ORBIT's ARM board workflows..."
  sudo apt-get update
  sudo apt-get install -y "${APT_PACKAGES[@]}"
}

setup_pico_sdk() {
  if [[ ! -d "${PICO_SDK_PATH_DEFAULT}/.git" ]]; then
    info "Cloning pico-sdk into ${PICO_SDK_PATH_DEFAULT}..."
    git clone https://github.com/raspberrypi/pico-sdk.git "${PICO_SDK_PATH_DEFAULT}"
  else
    info "pico-sdk already exists at ${PICO_SDK_PATH_DEFAULT}; leaving clone in place."
  fi

  info "Initializing pico-sdk submodules..."
  git -C "${PICO_SDK_PATH_DEFAULT}" submodule update --init
  export PICO_SDK_PATH="${PICO_SDK_PATH_DEFAULT}"
}

setup_stm32cube() {
  if [[ ! -d "${STM32CUBE_F4_PATH_DEFAULT}/.git" ]]; then
    info "Cloning STM32CubeF4 into ${STM32CUBE_F4_PATH_DEFAULT}..."
    git clone --depth 1 https://github.com/STMicroelectronics/STM32CubeF4.git "${STM32CUBE_F4_PATH_DEFAULT}"
  else
    info "STM32CubeF4 already exists at ${STM32CUBE_F4_PATH_DEFAULT}; leaving clone in place."
  fi

  info "Initializing STM32CubeF4 submodules..."
  git -C "${STM32CUBE_F4_PATH_DEFAULT}" submodule update --init --recursive
  export STM32CUBE_F4_PATH="${STM32CUBE_F4_PATH_DEFAULT}"
}

setup_nrf5_sdk() {
  if [[ -d "${NRF5_SDK_PATH_DEFAULT}" ]]; then
    info "nRF5 SDK already exists at ${NRF5_SDK_PATH_DEFAULT}; leaving it in place."
  else
    info "nRF5 SDK not found at ${NRF5_SDK_PATH_DEFAULT}."
    info "Place the Nordic nRF5 SDK there, or export NRF5_SDK_PATH to your SDK location."
  fi

  export NRF5_SDK_PATH="${NRF5_SDK_PATH_DEFAULT}"
}

check_nordic_host_tools() {
  if command -v nrfjprog >/dev/null 2>&1; then
    info "Found nrfjprog on PATH."
  else
    info "nrfjprog not found on PATH; install Nordic Command Line Tools for nRF52 flashing."
  fi

  if command -v JLinkExe >/dev/null 2>&1 || command -v JLinkGDBServer >/dev/null 2>&1; then
    info "Found Segger J-Link tooling on PATH."
  else
    info "Segger J-Link tools not found on PATH; install them if your Nordic workflow needs them."
  fi
}

setup_picotool_source() {
  if [[ ! -d "${REPO_ROOT}/picotool/.git" ]]; then
    info "picotool source not found in the repository checkout; cloning it into ${REPO_ROOT}/picotool..."
    rm -rf "${REPO_ROOT}/picotool"
    git clone "${PICOTOOL_REPO_URL}" "${REPO_ROOT}/picotool"
  else
    info "picotool source already exists at ${REPO_ROOT}/picotool."
  fi
}

install_picotool() {
  setup_picotool_source
  info "Building and installing picotool from the vendored source tree..."
  cmake -S "${REPO_ROOT}/picotool" -B "${REPO_ROOT}/picotool/build" \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX="${PICO_TOOL_PREFIX}"
  cmake --build "${REPO_ROOT}/picotool/build" --parallel
  cmake --install "${REPO_ROOT}/picotool/build"
}

install_picotool_udev_rules() {
  if [[ -f /etc/udev/rules.d/60-picotool.rules ]]; then
    info "picotool udev rules already installed."
    return
  fi

  info "Installing picotool udev rules..."
  sudo install -m 0644 "${REPO_ROOT}/picotool/udev/60-picotool.rules" /etc/udev/rules.d/60-picotool.rules
  if command -v udevadm >/dev/null 2>&1; then
    sudo udevadm control --reload-rules || true
    sudo udevadm trigger || true
  fi
}

setup_python_env() {
  if [[ ! -d "${REPO_ROOT}/.venv" ]]; then
    info "Creating Python virtual environment at ${REPO_ROOT}/.venv..."
    python3 -m venv "${REPO_ROOT}/.venv"
  else
    info "Virtual environment already exists at ${REPO_ROOT}/.venv."
  fi

  info "Installing Python requirements..."
  "${REPO_ROOT}/.venv/bin/pip" install --upgrade pip
  "${REPO_ROOT}/.venv/bin/pip" install -r "${REPO_ROOT}/requirements.txt"
}

setup_mount_point() {
  info "Ensuring /mnt/pico exists..."
  sudo mkdir -p /mnt/pico
}

setup_sudoers_mount_rule() {
  local current_user
  local temp_file
  current_user="$(id -un)"
  temp_file="$(mktemp)"

  cat > "${temp_file}" <<EOF
${current_user} ALL=(root) NOPASSWD: /usr/bin/mount, /usr/bin/umount, /bin/mount, /bin/umount
EOF

  info "Installing limited sudoers rule for Pico mount and unmount..."
  sudo visudo -cf "${temp_file}"
  sudo install -m 0440 "${temp_file}" "${SUDOERS_FILE}"
  rm -f "${temp_file}"
}

update_shell_profile() {
  local shell_rc
  shell_rc="${HOME}/.bashrc"

  info "Recording environment variables in ${shell_rc}..."
  append_line_if_missing 'export PATH="$HOME/.local/bin:$PATH"' "${shell_rc}"
  append_line_if_missing "export PICO_SDK_PATH=\"${PICO_SDK_PATH_DEFAULT}\"" "${shell_rc}"
  append_line_if_missing "export STM32CUBE_F4_PATH=\"${STM32CUBE_F4_PATH_DEFAULT}\"" "${shell_rc}"
  append_line_if_missing "export NRF5_SDK_PATH=\"${NRF5_SDK_PATH_DEFAULT}\"" "${shell_rc}"
  append_line_if_missing 'export picotool_DIR="$HOME/.local/picotool"' "${shell_rc}"
}

print_next_steps() {
  cat <<EOF

[setup] Completed.

Next steps:
  1. Reload your shell: source ~/.bashrc
  2. Activate the virtual environment: source .venv/bin/activate
  3. Verify host prerequisites: python3 tools/orbit.py --check
  4. Run a benchmark, for example:
     python3 tools/orbit.py --board pico --algo ascon_aead128 --runs 5 --flash
  5. For nRF52, make sure NRF5_SDK_PATH points at your nRF5 SDK and that nrfjprog is on PATH

EOF
}

main() {
  ensure_command git
  ensure_command python3

  install_apt_dependencies
  setup_pico_sdk
  setup_stm32cube
  setup_nrf5_sdk
  check_nordic_host_tools
  install_picotool
  install_picotool_udev_rules
  setup_python_env
  setup_mount_point
  setup_sudoers_mount_rule
  update_shell_profile
  print_next_steps
}

main "$@"
