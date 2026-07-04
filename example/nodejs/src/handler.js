/**
 * Hello World handler — Node.js example for sam-pipeline.
 */

"use strict";

/**
 * @param {import('aws-lambda').APIGatewayProxyEvent} event
 * @returns {Promise<import('aws-lambda').APIGatewayProxyResult>}
 */
exports.handler = async (event) => {
  console.log("Event:", JSON.stringify(event, null, 2));

  return {
    statusCode: 200,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message: "Hello from sam-pipeline!",
      account: process.env.AWS_ACCOUNT_ID ?? "unknown",
      region: process.env.AWS_REGION ?? "unknown",
    }),
  };
};
