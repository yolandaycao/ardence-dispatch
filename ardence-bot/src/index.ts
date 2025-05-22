import * as restify from 'restify';
import * as dotenv from 'dotenv';

// Load environment variables from .env file
dotenv.config();

// Import required bot services.
// See https://aka.ms/bot-services to learn more about the different parts of a bot.
import {
    CloudAdapter,
    ConfigurationServiceClientCredentialFactory,
    createBotFrameworkAuthenticationFromConfiguration
} from 'botbuilder';

// This bot's main dialog.
import { EmptyBot } from './bot';

// Create HTTP server.
const server = restify.createServer();
server.use(restify.plugins.bodyParser());

server.listen(process.env.port || process.env.PORT || 3978, () => {
    console.log(`\n${ server.name } listening to ${ server.url }`);
});

const credentialsFactory = new ConfigurationServiceClientCredentialFactory({
    MicrosoftAppId: process.env.TEAMS_BOT_APP_ID,
    MicrosoftAppPassword: process.env.TEAMS_BOT_APP_PASSWORD,
});

const botFrameworkAuthentication = createBotFrameworkAuthenticationFromConfiguration(null, credentialsFactory);

// Create adapter.
// See https://aka.ms/about-bot-adapter to learn more about adapters.
const adapter = new CloudAdapter(botFrameworkAuthentication);

// Catch-all for errors.
adapter.onTurnError = async (context, error) => {
    // This check writes out errors to console log .vs. app insights.
    // NOTE: In production environment, you should consider logging this to Azure
    //       application insights.
    console.error(`\n [onTurnError] unhandled error: ${ error }`);

    // Send a trace activity, which will be displayed in Bot Framework Emulator
    await context.sendTraceActivity(
        'OnTurnError Trace',
        `${ error }`,
        'https://www.botframework.com/schemas/error',
        'TurnError'
    );

    // Log error but don't send to user
    console.error('Bot encountered an error:', error);
};

// Create the main dialog.
const myBot = new EmptyBot();

// Listen for incoming requests.
server.post('/api/messages', async (req, res) => {
    // Route received a request to adapter for processing
    await adapter.process(req, res, (context) => myBot.run(context));
});

// Teams notification endpoint
server.post('/notify', async (req, res) => {
    try {
        const { ticketId, assignedTo, summary } = req.body;
        
        // Log the notification details
        console.log('Notification received:', {
            ticketId,
            assignedTo,
            summary
        });
        
        // Get the Teams channel ID from environment variables
        const channelId = process.env.TEAMS_CHANNEL_ID;
        if (!channelId) {
            console.error('TEAMS_CHANNEL_ID not configured in environment variables');
            return res.send(500, 'Teams channel ID not configured');
        }
        
        try {
            // Create an Adaptive Card
            const cardJson = {
                "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                "type": "AdaptiveCard",
                "version": "1.2",
                "body": [
                    {
                        "type": "TextBlock",
                        "size": "Medium",
                        "weight": "Bolder",
                        "text": "🎫 New Ticket Assigned"
                    },
                    {
                        "type": "TextBlock",
                        "text": `New ticket #${ticketId} has been assigned to ${assignedTo}.`,
                        "wrap": true
                    },
                    {
                        "type": "TextBlock",
                        "text": `Summary: ${summary}`,
                        "wrap": true
                    }
                ],
                "actions": [
                    {
                        "type": "Action.OpenUrl",
                        "title": "View Ticket",
                        "url": `https://cloudavize.syncromsp.com/tickets/${ticketId}`
                    }
                ]
            };
            
            // Create a conversation reference for the Teams channel
            const reference = {
                serviceUrl: "https://smba.trafficmanager.net/amer/",
                channelId: "msteams",
                conversation: {
                    id: channelId,
                    isGroup: true,
                    conversationType: "channel",
                    name: "Teams Channel"
                }
            };
            
            // Send the notification to Teams
            const appId = process.env.TEAMS_BOT_APP_ID;
            
            // Create a callback for after the conversation reference is established
            const logic = async (context) => {
                // Send the adaptive card
                await context.sendActivity({
                    type: "message",
                    attachments: [{
                        contentType: "application/vnd.microsoft.card.adaptive",
                        content: cardJson
                    }]
                });
            };
            
            // Send the notification to Teams
            await adapter.continueConversationAsync(
                appId,
                reference,
                logic
            );
            
            res.send(200, 'Notification sent to Teams');
        } catch (teamsError) {
            console.error('Error sending to Teams:', teamsError);
            // Log error but return success to avoid retries
            console.error('Teams delivery failed but continuing silently');
            res.send(200, 'OK');
        }
    } catch (error) {
        console.error('Error processing notification:', error);
        // Log error but return success to avoid retries
        console.error('Failed to process notification but continuing silently');
        res.send(200, 'OK');
    }
});
