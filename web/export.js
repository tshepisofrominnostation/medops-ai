/* Export formats for the console page.
 *
 * Kept separate from the UI so node can test them directly: what this file emits has to
 * be what app/importer.py accepts, or "export for import" is a dead end.
 * tests/test_export_contract.py loads this file, runs it, and feeds the output to the
 * real Python importer.
 */
var MedOpsExport = (function () {
  'use strict';

  function csvCell(value) {
    var text = String(value === undefined || value === null ? '' : value);
    return '"' + text.replace(/"/g, '""') + '"';
  }

  function toCsv(tickets) {
    var head = ['ticket_id', 'timestamp', 'sender', 'category', 'priority',
                'assigned_to', 'status', 'message', 'summary'];
    var lines = [head.join(',')];
    tickets.forEach(function (ticket) {
      lines.push([
        ticket.id, ticket.created_at, ticket.sender, ticket.category, ticket.priority,
        ticket.assigned_to, ticket.status, ticket.message, ticket.summary
      ].map(csvCell).join(','));
    });
    return lines.join('\n') + '\n';
  }

  /* Exactly the shape app.importer.import_tickets() validates. */
  function toExport(tickets) {
    return JSON.stringify({
      tickets: tickets.map(function (ticket) {
        return {
          sender: ticket.sender,
          category: ticket.category,
          priority: ticket.priority,
          summary: ticket.summary,
          assigned_to: ticket.assigned_to,
          timestamp: ticket.created_at
        };
      })
    }, null, 2);
  }

  return { toCsv: toCsv, toExport: toExport };
})();

if (typeof module !== 'undefined' && module.exports) module.exports = MedOpsExport;
