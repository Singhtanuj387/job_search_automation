import React from 'react';

/**
 * Parses inline markdown: **bold**, *italic*, `code`, and [text](url)
 */
function parseInline(text) {
  if (!text) return null;

  // Regex tokens: [text](url) | `code` | **bold** | *italic*
  const tokenRegex = /(\[.*?\]\(https?:\/\/[^\s)]+\)|`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*)/g;
  const parts = text.split(tokenRegex);

  return parts.map((part, i) => {
    if (!part) return null;

    // Link: [label](url)
    const linkMatch = part.match(/^\[(.*?)\]\((https?:\/\/[^\s)]+)\)$/);
    if (linkMatch) {
      return (
        <a
          key={i}
          href={linkMatch[2]}
          target="_blank"
          rel="noopener noreferrer"
          className="chat-link"
        >
          {linkMatch[1]}
        </a>
      );
    }

    // Inline Code: `code`
    if (part.startsWith('`') && part.endsWith('`') && part.length >= 2) {
      return (
        <code key={i} className="chat-inline-code">
          {part.slice(1, -1)}
        </code>
      );
    }

    // Bold: **text**
    if (part.startsWith('**') && part.endsWith('**') && part.length >= 4) {
      return (
        <strong key={i} className="chat-strong">
          {part.slice(2, -2)}
        </strong>
      );
    }

    // Italic: *text*
    if (part.startsWith('*') && part.endsWith('*') && part.length >= 2) {
      return (
        <em key={i} className="chat-em">
          {part.slice(1, -1)}
        </em>
      );
    }

    return part;
  });
}

/**
 * Renders a clean HTML table from markdown table lines
 */
function renderMarkdownTable(tableLines, key) {
  if (tableLines.length < 2) return null;

  const headerCells = tableLines[0]
    .split('|')
    .slice(1, -1)
    .map(c => c.trim());

  const rowLines = tableLines.slice(2);

  return (
    <div key={key} className="table-responsive-wrapper">
      <table className="clean-chat-table">
        <thead>
          <tr>
            {headerCells.map((h, hIdx) => (
              <th key={hIdx}>{parseInline(h)}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rowLines.map((rowStr, rIdx) => {
            const cells = rowStr
              .split('|')
              .slice(1, -1)
              .map(c => c.trim());
            if (cells.length === 0 || (cells.length === 1 && !cells[0])) return null;
            return (
              <tr key={rIdx}>
                {cells.map((cell, cIdx) => (
                  <td key={cIdx}>{parseInline(cell)}</td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/**
 * Formats full chat messages into clean HTML elements,
 * stripping ugly raw markdown noise (*, #, |) and turning tables into real HTML tables.
 */
export default function FormattedMessage({ content, stripTable = false }) {
  if (!content) return null;

  const lines = content.split('\n');
  const elements = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];
    const trimmed = line.trim();

    // 1. Detect and parse Markdown Table
    const isTableStart =
      (trimmed.startsWith('|') || trimmed.startsWith('# |') || trimmed.includes('| Job Title |')) &&
      i + 1 < lines.length &&
      lines[i + 1].trim().includes('---');

    if (isTableStart) {
      const tableLines = [];
      while (
        i < lines.length &&
        (lines[i].trim().startsWith('|') || lines[i].trim().startsWith('# |') || lines[i].trim().includes('|')) &&
        lines[i].trim().length > 0
      ) {
        let cleanRow = lines[i].trim();
        if (cleanRow.startsWith('# |')) {
          cleanRow = cleanRow.slice(2);
        }
        if (!cleanRow.startsWith('|')) cleanRow = '| ' + cleanRow;
        if (!cleanRow.endsWith('|')) cleanRow = cleanRow + ' |';
        tableLines.push(cleanRow);
        i++;
      }
      if (!stripTable) {
        elements.push(renderMarkdownTable(tableLines, `tbl_${elements.length}`));
      }
      continue;
    }

    // 2. Empty line
    if (!trimmed) {
      i++;
      continue;
    }

    // 3. Headings: ### or ## or #
    if (trimmed.startsWith('### ')) {
      elements.push(
        <h4 key={`h4_${i}`} className="chat-heading-3">
          {parseInline(trimmed.slice(4))}
        </h4>
      );
      i++;
      continue;
    }
    if (trimmed.startsWith('## ')) {
      elements.push(
        <h3 key={`h3_${i}`} className="chat-heading-2">
          {parseInline(trimmed.slice(3))}
        </h3>
      );
      i++;
      continue;
    }
    if (trimmed.startsWith('# ')) {
      elements.push(
        <h2 key={`h2_${i}`} className="chat-heading-1">
          {parseInline(trimmed.slice(2))}
        </h2>
      );
      i++;
      continue;
    }

    // 4. Blockquote / Alert: >
    if (trimmed.startsWith('> ')) {
      const quoteLines = [];
      while (i < lines.length && lines[i].trim().startsWith('>')) {
        quoteLines.push(lines[i].trim().replace(/^>\s*/, ''));
        i++;
      }
      elements.push(
        <div key={`quote_${i}`} className="chat-callout">
          {quoteLines.map((q, qIdx) => (
            <div key={qIdx}>{parseInline(q)}</div>
          ))}
        </div>
      );
      continue;
    }

    // 5. Unordered List: - or *
    if (trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
      const listItems = [];
      while (i < lines.length && (lines[i].trim().startsWith('- ') || lines[i].trim().startsWith('* '))) {
        listItems.push(lines[i].trim().slice(2));
        i++;
      }
      elements.push(
        <ul key={`ul_${i}`} className="chat-list">
          {listItems.map((item, lIdx) => (
            <li key={lIdx} className="chat-list-item">
              {parseInline(item)}
            </li>
          ))}
        </ul>
      );
      continue;
    }

    // 6. Numbered List: 1. 2. etc.
    const numMatch = trimmed.match(/^\d+\.\s+(.*)$/);
    if (numMatch) {
      const numItems = [];
      while (i < lines.length) {
        const match = lines[i].trim().match(/^\d+\.\s+(.*)$/);
        if (match) {
          numItems.push(match[1]);
          i++;
        } else {
          break;
        }
      }
      elements.push(
        <ol key={`ol_${i}`} className="chat-ordered-list">
          {numItems.map((item, oIdx) => (
            <li key={oIdx} className="chat-ordered-item">
              {parseInline(item)}
            </li>
          ))}
        </ol>
      );
      continue;
    }

    // 7. Regular paragraph
    elements.push(
      <p key={`p_${i}`} className="chat-para">
        {parseInline(trimmed)}
      </p>
    );
    i++;
  }

  return <div className="formatted-chat-content">{elements}</div>;
}
