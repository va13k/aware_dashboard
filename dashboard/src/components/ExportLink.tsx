interface Props {
  href: string;
  label?: string;
  title?: string;
  className?: string;
}

export default function ExportLink({
  href,
  label = "CSV",
  title = "Export CSV",
  className = "",
}: Props) {
  return (
    <a
      href={href}
      title={title}
      className={`inline-flex h-7 items-center justify-center rounded-lg border border-wire bg-card-strong px-2 text-[10px] font-semibold uppercase tracking-[0.4px] text-sage transition-colors hover:border-teal hover:text-teal ${className}`}
    >
      {label}
    </a>
  );
}
