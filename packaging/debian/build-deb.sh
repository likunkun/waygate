#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PACKAGE_NAME="waygate"
_PKG_VERSION="$(python3 -c "import sys; sys.path.insert(0, '${ROOT_DIR}'); from workflow_controller import __version__; print(__version__)")"
VERSION="${WAYGATE_VERSION:-${_PKG_VERSION}}"
ARCHITECTURE="all"
DIST_DIR="${WAYGATE_DIST_DIR:-"${ROOT_DIR}/dist"}"
BUILD_ROOT="${WAYGATE_BUILD_ROOT:-"${ROOT_DIR}/.build/debian"}"
PACKAGE_DIR="${BUILD_ROOT}/${PACKAGE_NAME}_${VERSION}_${ARCHITECTURE}"
DEB_PATH="${DIST_DIR}/${PACKAGE_NAME}_${VERSION}_${ARCHITECTURE}.deb"

rm -rf "${PACKAGE_DIR}"
mkdir -p \
  "${PACKAGE_DIR}/DEBIAN" \
  "${PACKAGE_DIR}/usr/bin" \
  "${PACKAGE_DIR}/usr/lib/${PACKAGE_NAME}" \
  "${PACKAGE_DIR}/usr/share/doc/${PACKAGE_NAME}" \
  "${PACKAGE_DIR}/usr/share/doc/${PACKAGE_NAME}/docs" \
  "${DIST_DIR}"

cp -a "${ROOT_DIR}/workflow_controller" "${PACKAGE_DIR}/usr/lib/${PACKAGE_NAME}/"
rm -rf "${PACKAGE_DIR}/usr/lib/${PACKAGE_NAME}/workflow_controller/tests"
find "${PACKAGE_DIR}/usr/lib/${PACKAGE_NAME}/workflow_controller" \
  \( -type d -name '__pycache__' -o -type d -name '.pytest_cache' \) -prune -exec rm -rf {} +
find "${PACKAGE_DIR}/usr/lib/${PACKAGE_NAME}/workflow_controller" \
  -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete

install -m 0644 "${ROOT_DIR}/README.md" "${PACKAGE_DIR}/usr/share/doc/${PACKAGE_NAME}/README.md"
install -m 0644 "${ROOT_DIR}/README.zh-CN.md" "${PACKAGE_DIR}/usr/share/doc/${PACKAGE_NAME}/README.zh-CN.md"
install -m 0644 "${ROOT_DIR}/USAGE.md" "${PACKAGE_DIR}/usr/share/doc/${PACKAGE_NAME}/USAGE.md"
install -m 0644 "${ROOT_DIR}/USAGE.zh-CN.md" "${PACKAGE_DIR}/usr/share/doc/${PACKAGE_NAME}/USAGE.zh-CN.md"
install -m 0644 "${ROOT_DIR}/ROADMAP.md" "${PACKAGE_DIR}/usr/share/doc/${PACKAGE_NAME}/ROADMAP.md"
install -m 0644 "${ROOT_DIR}/ROADMAP.zh-CN.md" "${PACKAGE_DIR}/usr/share/doc/${PACKAGE_NAME}/ROADMAP.zh-CN.md"
install -m 0644 "${ROOT_DIR}/CHANGELOG.md" "${PACKAGE_DIR}/usr/share/doc/${PACKAGE_NAME}/CHANGELOG.md"
install -m 0644 "${ROOT_DIR}/CHANGELOG.zh-CN.md" "${PACKAGE_DIR}/usr/share/doc/${PACKAGE_NAME}/CHANGELOG.zh-CN.md"
install -m 0644 "${ROOT_DIR}/LICENSE" "${PACKAGE_DIR}/usr/share/doc/${PACKAGE_NAME}/LICENSE"
install -m 0644 "${ROOT_DIR}/docs/architecture.md" "${PACKAGE_DIR}/usr/share/doc/${PACKAGE_NAME}/docs/architecture.md"
install -m 0644 "${ROOT_DIR}/docs/architecture.zh-CN.md" "${PACKAGE_DIR}/usr/share/doc/${PACKAGE_NAME}/docs/architecture.zh-CN.md"
install -m 0644 "${ROOT_DIR}/docs/workflow.md" "${PACKAGE_DIR}/usr/share/doc/${PACKAGE_NAME}/docs/workflow.md"
install -m 0644 "${ROOT_DIR}/docs/workflow.zh-CN.md" "${PACKAGE_DIR}/usr/share/doc/${PACKAGE_NAME}/docs/workflow.zh-CN.md"

cat > "${PACKAGE_DIR}/DEBIAN/control" <<EOF
Package: ${PACKAGE_NAME}
Version: ${VERSION}
Section: devel
Priority: optional
Architecture: ${ARCHITECTURE}
Depends: python3
Maintainer: Waygate Maintainers <root@localhost>
Description: Waygate workflow control surface for AI coding delivery
 Waygate coordinates requirements, unit planning, implementation,
 verification, and final acceptance gates for auditable AI coding work.
EOF

cat > "${PACKAGE_DIR}/usr/bin/${PACKAGE_NAME}" <<'EOF'
#!/usr/bin/env sh
export PYTHONPATH="/usr/lib/waygate${PYTHONPATH:+:$PYTHONPATH}"
exec python3 -m workflow_controller.cli "$@"
EOF
chmod 0755 "${PACKAGE_DIR}/usr/bin/${PACKAGE_NAME}"

dpkg-deb --build --root-owner-group "${PACKAGE_DIR}" "${DEB_PATH}"
printf '%s\n' "${DEB_PATH}"
