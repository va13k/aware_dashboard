interface Props {
  href: string;
  label?: string;
  title?: string;
  className?: string;
  disabled?: boolean;
}

export default function ExportLink({
  href,
  label = "CSV",
  title = "Export CSV",
  className = "",
  disabled = false,
}: Props) {
  const base = `inline-flex h-7 items-center justify-center rounded-lg border px-2 text-[10px] font-semibold uppercase tracking-[0.4px] ${className}`;

  if (disabled) {
    return (
      <span
        title="No records to export"
        className={`${base} cursor-not-allowed border-wire bg-card-strong text-sage/30`}
      >
        {label}
      </span>
    );
  }

  return (
    <a
      href={href}
      title={title}
      className={`${base} border-wire bg-card-strong text-sage transition-colors hover:border-teal hover:text-teal`}
    >
      {label}
    </a>
  );
}
