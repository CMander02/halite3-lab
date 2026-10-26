import { Fragment, type ReactNode } from "react";

/** Inline `code` and **bold**. */
function inline(text: string): ReactNode[] {
  return text.split(/(`[^`]+`|\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith("`") && part.endsWith("`") && part.length > 1 ? (
      <code key={i} className="border border-line bg-paper-2 px-1 font-mono text-[14px]">
        {part.slice(1, -1)}
      </code>
    ) : part.startsWith("**") && part.endsWith("**") && part.length > 3 ? (
      <strong key={i} className="font-bold text-ink">
        {part.slice(2, -2)}
      </strong>
    ) : (
      <Fragment key={i}>{part}</Fragment>
    ),
  );
}

/** Just enough Markdown for generated rules and prompts: headings, lists, code blocks, paragraphs. */
export function Markdown({ text, skipTitle = false }: { text: string; skipTitle?: boolean }) {
  const blocks: ReactNode[] = [];
  const lines = text.split("\n");
  let list: string[] = [];
  const flush = () => {
    if (list.length)
      blocks.push(
        <ul key={blocks.length} className="my-2 flex list-none flex-col gap-1.5 p-0">
          {list.map((item, i) => (
            <li key={i} className="relative pl-4 before:absolute before:left-0 before:text-blue before:content-['■'] before:text-[8px] before:leading-[26px]">
              {inline(item)}
            </li>
          ))}
        </ul>,
      );
    list = [];
  };
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (line.startsWith("```")) {
      flush();
      const body: string[] = [];
      while (++i < lines.length && !lines[i].startsWith("```")) body.push(lines[i]);
      blocks.push(
        <pre key={blocks.length} className="my-2 overflow-x-auto border border-line bg-paper-2 p-3 font-mono text-[14px] leading-[22px]">
          {body.join("\n")}
        </pre>,
      );
    } else if (line.startsWith("- ")) list.push(line.slice(2));
    else {
      flush();
      if (line.startsWith("# ")) {
        if (!skipTitle) blocks.push(<h2 key={blocks.length} className="mt-0 mb-3 text-[22px] leading-[30px] font-bold">{line.slice(2)}</h2>);
      } else if (line.startsWith("## ")) blocks.push(<h3 key={blocks.length} className="mt-6 mb-1 text-[18px] leading-[28px] font-bold text-ink first:mt-0">{line.slice(3)}</h3>);
      else if (line.trim()) blocks.push(<p key={blocks.length} className="my-2">{inline(line)}</p>);
    }
  }
  flush();
  return <div className="leading-[28px] text-ink-2">{blocks}</div>;
}
