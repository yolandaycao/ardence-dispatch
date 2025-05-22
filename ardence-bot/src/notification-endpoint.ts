import * as express from 'express';
import { TeamsNotifier, TicketNotification } from './teams-notifier';

export function setupNotificationEndpoint(app: express.Express, notifier: TeamsNotifier) {
    app.post('/notify', async (req, res) => {
        try {
            const notification: TicketNotification = req.body;
            await notifier.sendTicketNotification(notification);
            res.status(200).send('Notification sent successfully');
        } catch (error) {
            console.error('Error sending notification:', error);
            res.status(500).send('Failed to send notification');
        }
    });
}
