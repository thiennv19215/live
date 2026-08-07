export function resolveOutputStatus(savedHidden, status) {
  const open = Boolean(status?.open);
  const hidden = open && typeof status?.hidden === "boolean"
    ? status.hidden
    : Boolean(savedHidden);
  return { open, hidden };
}

export function resolveHiddenChange(status) {
  if (!status?.open) {
    throw new Error("Output không còn mở");
  }
  if (typeof status.hidden !== "boolean") {
    throw new Error("Không xác nhận được trạng thái Output");
  }
  return status.hidden;
}
