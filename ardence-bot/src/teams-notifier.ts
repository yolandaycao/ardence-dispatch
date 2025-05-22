import { MicrosoftAppCredentials, ConnectorClient } from 'botframework-connector';

export interface TicketNotification {
    ticketId: number;
    subject: string;
    assignedTo: string;
    teamsMention: string;
    category: string;
    priority?: string;
}

export class TeamsNotifier {
    private credentials: MicrosoftAppCredentials;
    private channelId: string;
    private serviceUrl: string = 'https://smba.trafficmanager.net/amer/';

    constructor(appId: string, appPassword: string, channelId: string) {
        this.credentials = new MicrosoftAppCredentials(appId, appPassword);
        this.channelId = channelId;
    }

    async sendTicketNotification(notification: TicketNotification): Promise<void> {
        const client = new ConnectorClient(this.credentials, { baseUri: this.serviceUrl });

        const message = {
            type: 'message',
            channelId: 'msteams',
            conversation: {
                id: this.channelId,
                name: 'dispatch',
                conversationType: 'channel',
                isGroup: true
            },
            text: this.formatMessage(notification),
        };

        await client.conversations.sendToConversation(this.channelId, message);
    }

    private formatMessage(notification: TicketNotification): string {
        return `🎫 **New Ticket Assignment**\n\n` +
               `**Ticket #${notification.ticketId}**\n` +
               `**Subject:** ${notification.subject}\n` +
               `**Category:** ${notification.category}\n` +
               `${notification.priority ? `**Priority:** ${notification.priority}\n` : ''}` +
               `**Assigned To:** ${notification.teamsMention}\n\n` +
               `Please review and acknowledge this ticket.`;
    }
}
