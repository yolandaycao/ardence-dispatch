import { TurnContext, TeamsActivityHandler } from 'botbuilder';

export class EmptyBot extends TeamsActivityHandler {
    constructor() {
        super();

        this.onMessage(async (context, next) => {
            // Log user information for ID lookup
            console.log('User Info:', {
                id: context.activity.from.id,
                name: context.activity.from.name,
                aadObjectId: context.activity.from.aadObjectId
            });
            
            // If user asks for their ID, send it back
            if (context.activity.text.toLowerCase().includes('my id')) {
                await context.sendActivity(`Your Teams ID: ${context.activity.from.id}\nYour AAD ID: ${context.activity.from.aadObjectId || 'Not available'}`);
            } else {
                await context.sendActivity(`You said '${context.activity.text}'`);
            }
            
            await next();
        });

        this.onMembersAdded(async (context, next) => {
            const membersAdded = context.activity.membersAdded;
            const welcomeText = 'Hello! Send "my id" to see your Teams user ID.';
            for (const member of membersAdded) {
                if (member.id !== context.activity.recipient.id) {
                    await context.sendActivity(welcomeText);
                }
            }
            await next();
        });
    }
}
